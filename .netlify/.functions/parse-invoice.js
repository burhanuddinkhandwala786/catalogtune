exports.handler = async (event, context) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method Not Allowed' }) };
  }

  try {
    const { imageBase64 } = JSON.parse(event.body);

    if (!imageBase64) {
      return { statusCode: 400, headers, body: JSON.stringify({ error: 'No image provided' }) };
    }

    const apiKey = process.env.OPENROUTER_API_KEY;

    const prompt = `
    Extract all product line items from this catalog or invoice image.
    For each item, extract:
    1. Product Name (include finish, variant, or dimensions if present)
    2. SKU / Item Code
    3. HSN Code (4 or 6 digits)
    4. Price / MRP (numeric value only)
    5. Unit (e.g., Pcs, Set)

    Return STRICTLY a JSON object with key "items" containing an array of objects with keys:
    "itemName", "itemCode", "hsnCode", "salesPrice", "unit"
    `;

    const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: "google/gemini-2.0-flash-lite-001", // Fast, accurate vision model with a free tier
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: prompt },
              {
                type: "image_url",
                image_url: { url: `data:image/jpeg;base64,${imageBase64}` }
              }
            ]
          }
        ]
      })
    });

    const data = await response.json();
    if (data.error) throw new Error(data.error.message || JSON.stringify(data.error));

    let content = data.choices[0].message.content;
    
    // Clean JSON formatting if model wraps output in markdown code blocks
    content = content.replace(/```json/g, '').replace(/```/g, '').trim();
    
    const parsedData = JSON.parse(content);
    const rawItems = parsedData.items || [];

    // Format & enforce Accountune rules
    const formattedItems = rawItems.map(item => {
      let cleanPrice = String(item.salesPrice || '0').replace(/[^\d.]/g, '');
      let hsn = String(item.hsnCode || '83014090').replace(/[^\d]/g, '');

      return {
        "Item Name": item.itemName || 'Unnamed Product',
        "Item Code / SKU": item.itemCode || 'N/A',
        "HSN Code": hsn || '83014090',
        "Sales Price": parseFloat(cleanPrice) || 0,
        "Tax Rate (%)": "18%",
        "Primary Unit": item.unit || 'Pcs',
        "Opening Stock": 0 // Enforce 0 opening stock strictly
      };
    });

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ success: true, items: formattedItems })
    };

  } catch (error) {
    console.error('Error processing image:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: error.message || 'Failed to process image' })
    };
  }
};
