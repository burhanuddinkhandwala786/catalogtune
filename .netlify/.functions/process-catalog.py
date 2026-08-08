import json
import base64
import re
import io
import pdfplumber

def handler(event, context):
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    if event.get('httpMethod') != 'POST':
        return {'statusCode': 405, 'headers': headers, 'body': json.dumps({'error': 'Method Not Allowed'})}

    try:
        body = json.loads(event.get('body', '{}'))
        file_base64 = body.get('fileBase64')

        if not file_base64:
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'No file data received'})}

        pdf_bytes = base64.b64decode(file_base64)
        pdf_file = io.BytesIO(pdf_bytes)

        extracted_items = []

        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    for row in table:
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        row_str = " ".join(clean_row).lower()

                        if not row_str or "product name" in row_str or "unspsc" in row_str or "backset" in row_str:
                            continue

                        cells = [c for c in clean_row if c]
                        if len(cells) < 3:
                            continue

                        # SKU Code matching
                        code_match = [c for c in cells if re.match(r'^\d{4}$', c)]
                        product_code = code_match[0] if code_match else cells[0]

                        # MRP Price matching
                        price_cells = [c for c in cells if re.search(r'\d+', c) and (' ' in c or '.' in c or ',' in c or c.isdigit())]
                        mrp = price_cells[-1] if price_cells else "0"
                        clean_mrp = re.sub(r'[^\d]', '', mrp)

                        # Product Name
                        name_cells = [c for c in cells if not re.match(r'^\d+$', c) and "sd" not in c.lower()]
                        product_name = " - ".join(name_cells[:2]) if name_cells else cells[0]

                        # HSN Code Assignment Rules
                        hsn_code = "83014090"
                        name_lower = product_name.lower()
                        if any(k in name_lower for k in ["padlock", "navtal", "duralock", "sherlock", "herculoc"]):
                            hsn_code = "83011000"
                        elif any(k in name_lower for k in ["furniture", "curvo", "nuvo", "cam lock", "drawer"]):
                            hsn_code = "83013000"
                        elif any(k in name_lower for k in ["closer", "hinge", "bolt", "handle"]):
                            hsn_code = "83024110"

                        if clean_mrp and clean_mrp != '0':
                            extracted_items.append({
                                "Item Name": product_name,
                                "Item Code / SKU": product_code,
                                "HSN Code": hsn_code,
                                "Sales Price": float(clean_mrp),
                                "Tax Rate (%)": "18%",
                                "Primary Unit": "Pcs",
                                "Opening Stock": 0
                            })

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'success': True, 'items': extracted_items})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }
