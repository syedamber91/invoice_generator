import pandas as pd
from pypdf import PdfReader
import re

def parse_pricing_pdf(pdf_path, output_excel):
    print(f"Reading {pdf_path}...")
    reader = PdfReader(pdf_path)
    
    items = []
    
    # Regex to match lines starting with a price (digits) followed by text
    # Example: "73 Plain Double Duvet Cover" or "73 Arabic Text"
    # Based on analysis: "73 Arabic Text" then next line "English Text"
    price_pattern = re.compile(r'^\s*(\d+(?:\.\d+)?)\s+(.+)$')
    
    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if line matches price pattern
            match = price_pattern.match(line)
            
            # Additional check to ensure the first part is likely a price and not just a numbered list
            # The prices seen were 73, 52, 44, etc. 
            # We can check if line matches, but we also want to avoid page numbers line "1" which might appear alone.
            
            if match:
                price_str = match.group(1)
                remainder = match.group(2)
                
                # Heuristic: If remainder is very short or just digits, maybe ignore?
                # But "1" (page number) would match text "1" if regex is \d+ .+
                # Actually regex requires a space then text, so "1" alone won't match.
                
                try:
                    price = float(price_str)
                except ValueError:
                    i += 1
                    continue

                arabic_desc = remainder.strip()
                english_desc = ""
                
                # Look ahead for English description
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    # Check if next line starts with English letter
                    if next_line and re.match(r'^[A-Za-z]', next_line):
                        english_desc = next_line
                        i += 1 # Consume next line
                
                # Construct Product Name
                # Clean up extracted text
                full_product_name = arabic_desc
                if english_desc:
                    full_product_name = f"{english_desc} - {arabic_desc}"
                
                # Filter out likely false positives (headers usually don't start with a number like "300 thread count" unless structure is weird)
                # But "300 غرزة" might be parsed as price 300 if at start of line.
                # In text: "السعر الصنف سادة 300 غرزة" -> Starts with Arabic, won't match digits first.
                
                items.append({
                    'Product': full_product_name,
                    'Quantity': 0, # Default to 0 so user can fill in
                    'Price': price
                })
            
            i += 1
            
    if not items:
        print("No items found! Check the PDF format.")
        return

    df = pd.DataFrame(items)
    print(f"Found {len(df)} items.")
    print(df.head())
    
    # Save to Excel
    df.to_excel(output_excel, index=False)
    print(f"Created {output_excel}")

if __name__ == "__main__":
    parse_pricing_pdf("Item_Pricing.pdf", "invoice_data_from_pdf.xlsx")
