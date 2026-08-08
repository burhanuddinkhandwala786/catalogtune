import json
import base64
import re
import io
import pdfplumber
import pandas as pd

def handler(event, context):
    # Enable CORS headers for Netlify
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }

    # Handle preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''
        }

    if event.get('httpMethod') != 'POST':
        return {
            'statusCode': 405,
            'headers': headers,
            'body': json.dumps({'error': 'Method Not Allowed'})
        }

    try:
        # Parse payload
        body = json.loads(event.get('body', '{}'))
        file_base64 = body.get('fileBase64')

        if not file_base64:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'No file uploaded'})
            }

        # Decode PDF from base64
        pdf_bytes = base64.b64decode(file_base64)
        pdf_file = io.BytesIO(pdf_bytes)

        all_rows = []

        # Native table extraction across all PDF pages
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    for row in table:
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        row_str = " ".join(clean_row).lower()
                        # Filter out table header noise
                        if not row_str or "product name" in row_str or "unspsc" in row_str or "backset" in row_str:
                            continue
                        all_rows.append(clean_row)

        processed_data = []
        for row in all_rows:
            cells = [c for c in row if c]
            if len(cells) < 3:
                continue

            # Extract 4-digit Product SKU Code
            code_match = [c for c in cells if re.match(r'^\d{4}$', c)]
            product_code = code_match[0] if code_match else cells[0]

            # Extract price MRP
            price_cells = [c for c in cells if re.search(r'\d+', c) and (' ' in c or '.' in c or ',' in c or c.isdigit())]
            mrp = price_cells[-1] if price_cells else "0"
            clean_mrp = re.sub(r'[^\d]', '', mrp)

            # Product Name
            name_cells = [c for c in cells if not re.match(r'^\d+$', c) and "sd" not in c.lower()]
            product_name = " - ".join(name_cells[:2]) if name_cells else cells[0]

            # Assign HSN Code rules
            hsn_code = "83014090"
            name_lower = product_name.lower()
            if any(k in name_lower for k in ["padlock", "navtal", "duralock", "sherlock", "herculoc"]):
                hsn_code = "83011000"
            elif any(k in name_lower for k in ["furniture", "curvo", "nuvo", "cam lock", "drawer"]):
                hsn_code = "83013000"
            elif any(k in name_lower for k in ["closer", "hinge", "bolt", "handle"]):
                hsn_code = "83024110"

            processed_data.append({
                "Item Name": product_name,
                "Item Code / SKU": product_code,
                "HSN Code": hsn_code,
                "Sales Price": float(clean_mrp) if clean_mrp else 0.0,
                "Tax Rate (%)": "18%",
                "Primary Unit": "Pcs",
                "Opening Stock": 0  # Forced 0 opening stock
            })

        df = pd.DataFrame(processed_data).drop_duplicates(subset=["Item Code / SKU"])

        # Convert to Excel Base64 output
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="Accountune_Master")
        excel_buffer.seek(0)

        excel_b64 = base64.b64encode(excel_buffer.read()).decode('utf-8')

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'itemsCount': len(df),
                'excelBase64': excel_b64
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }
