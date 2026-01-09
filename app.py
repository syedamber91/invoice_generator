import streamlit as st
import pandas as pd
import sqlite3
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter
import io
import os
import re

import arabic_reshaper
from bidi.algorithm import get_display

# --- Configuration ---
DB_FILE = "products.db"
# Use a font that supports Arabic. Arial usually does on Mac/Windows.
# We will try to load it from common paths or expect it in the folder.
# For robustness in this environment, I'll check a few paths.
FONT_PATH = "/Library/Fonts/Arial Unicode.ttf" # Mac common
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "Arial.ttf" # Fallback to local if user provides it

st.set_page_config(page_title="Dynamic Invoice Generator", layout="wide")

# --- Database Functions ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price REAL
        )
    ''')
    conn.commit()
    return conn

def load_products_from_db():
    conn = init_db()
    df = pd.read_sql("SELECT name as Product, price as Price FROM products ORDER BY name", conn)
    conn.close()
    return df

def save_products_to_db(df):
    if 'Product' not in df.columns or 'Price' not in df.columns:
        return False, "Data must have 'Product' and 'Price' columns."
        
    try:
        conn = init_db()
        c = conn.cursor()
        for index, row in df.iterrows():
            c.execute('''
                INSERT INTO products (name, price) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET price=excluded.price
            ''', (row['Product'], row['Price']))
        
        conn.commit()
        conn.close()
        return True, "Database updated successfully!"
    except Exception as e:
        if 'conn' in locals(): conn.close()
        return False, str(e)

def clear_db():
    conn = init_db()
    c = conn.cursor()
    c.execute("DELETE FROM products")
    conn.commit()
    conn.close()

# --- PDF Parsing Function (Adapted from generate_from_pdf.py) ---
def parse_pricing_pdf_stream(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        items = []
        price_pattern = re.compile(r'^\s*(\d+(?:\.\d+)?)\s+(.+)$')
        
        for page in reader.pages:
            text = page.extract_text()
            lines = text.split('\n')
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                match = price_pattern.match(line)
                
                if match:
                    price_str = match.group(1)
                    remainder = match.group(2)
                    
                    try:
                        price = float(price_str)
                    except ValueError:
                        i += 1
                        continue

                    arabic_desc = remainder.strip()
                    english_desc = ""
                    
                    if i + 1 < len(lines):
                        next_line = lines[i+1].strip()
                        if next_line and re.match(r'^[A-Za-z]', next_line):
                            english_desc = next_line
                            i += 1 
                    
                    full_product_name = arabic_desc
                    if english_desc:
                        full_product_name = f"{english_desc} - {arabic_desc}"
                    
                    items.append({
                        'Product': full_product_name,
                        'Price': price
                    })
                i += 1
        
        if not items:
            return None, "No items found in PDF."
            
        return pd.DataFrame(items), None
        
    except Exception as e:
        return None, f"Error parsing PDF: {e}"

# --- PDF Generation Logic ---
def generate_pdf(invoice_df, letterhead_bytes, grand_total, header_info):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    width, height = A4
    
    # Register Arabic Font
    try:
        pdfmetrics.registerFont(TTFont('ArabicFont', FONT_PATH))
        font_name = 'ArabicFont'
    except:
        st.error(f"Could not load font from {FONT_PATH}. Using default.")
        font_name = 'Helvetica'

    def process_text(text):
        if font_name == 'ArabicFont':
            reshaped_text = arabic_reshaper.reshape(str(text))
            bidi_text = get_display(reshaped_text)
            return bidi_text
        return str(text)

    # --- Header Table ---
    # Draw header info table (Date, Bill No, Customer, etc.)
    # Placement: Right half of the page (Center to Right)
    # A4 Width ~595. Center ~300. Right Margin ~565.
    
    can.setFont(font_name, 10)
    
    # Coordinates
    # Adjusted for better spacing below letterhead header
    table_top = 620 
    row_height = 20
    
    # Table bounds
    table_x = 300
    table_width = 265 # 565 - 300
    
    # --- Styling Helpers (Enhanced) ---
    def draw_styled_row(y, label, value, is_bold=False, align_value_right=False):
        # Configuration
        label_width_pct = 0.35
        label_w = table_width * label_width_pct
        value_w = table_width * (1 - label_width_pct)
        
        # Label Cell (Left)
        can.setFillColorRGB(0.95, 0.95, 0.95) # Light Grey
        can.rect(table_x, y - row_height, label_w, row_height, stroke=1, fill=1)
        
        # Value Cell (Right)
        can.setFillColorRGB(1, 1, 1) # White
        can.rect(table_x + label_w, y - row_height, value_w, row_height, stroke=1, fill=1)
        
        # Text
        can.setFillColorRGB(0, 0, 0) # Black Text
        can.setFont(font_name, 10 if not is_bold else 11)
        
        # Label Text (Left Aligned with padding)
        can.drawString(table_x + 5, y - 14, label)
        
        # Value Text
        val_text = process_text(value)
        if align_value_right:
             # Right align relative to the end of the value cell
             can.drawRightString(table_x + label_w + value_w - 5, y - 14, val_text)
        else:
             can.drawString(table_x + label_w + 5, y - 14, val_text)


    # --- Header Table ---
    can.setFont(font_name, 10)
    
    # 1. Date
    draw_styled_row(table_top, "Date", header_info['date'])
    table_top -= row_height
    
    # 2. Bill No
    draw_styled_row(table_top, "Bill No", str(header_info['bill_no']))
    table_top -= row_height
    
    # 3. Customer
    draw_styled_row(table_top, "Customer", header_info['customer'])
    table_top -= row_height
    
    # 4. Address
    draw_styled_row(table_top, "Address", header_info['address'])
    table_top -= row_height
    
    # 5. VAT No
    draw_styled_row(table_top, "VAT Number", header_info['vat_no'])
    table_top -= row_height
    
    # 6. Payment Terms
    draw_styled_row(table_top, "Payment Method", header_info['terms'])
    table_top -= row_height
    
    # --- Item Table Header ---
    y_pos = table_top - 60 # Increased spacing between Header Block and Items
    
    # Headers (RTL Format)
    # Right to Left: #, Code, Description, Qty, Price, TotalEx, VAT, TotalInc
    # Bounds: 30 to 565.
    
    headers = [
        (550, "#"),
        (500, "Code"),
        (390, "Description"), 
        (280, "Qty"),
        (235, "Unit Price"),
        (175, "Total (Excl)"),
        (115, "VAT (15%)"),
        (60, "Total (Incl)")
    ]
    
    can.setFont(font_name, 9)
    can.setFillColorRGB(0.9, 0.9, 0.9)
    can.rect(30, y_pos - 5, 535, 15, fill=1, stroke=0)
    can.setFillColorRGB(0, 0, 0)
    
    for x, title in headers:
        can.drawCentredString(x, y_pos, title)
        
    y_pos -= 25
    
    # Item Rows
    can.setFont(font_name, 9)
    
    index_counter = 1
    
    for index, row in invoice_df.iterrows():
        # Parsing Code from Product Name
        product_name = row['Product']
        item_code = ""
        
        code_match = re.match(r'^(\d+)\s+(.+)', product_name)
        if code_match:
            item_code = code_match.group(1)
            product_name = code_match.group(2)
        
        # Calculations
        qty = row['Quantity']
        price = row['Price']
        subtotal = row['Subtotal']
        tax = row['Tax (15%)']
        total_incl = row['Total']
        
        # Draw Columns (RTL Mapped)
        # 1. # (Far Right)
        can.drawCentredString(550, y_pos, str(index_counter))
        
        # 2. Code
        can.drawCentredString(500, y_pos, item_code)
        
        # 3. Description
        display_name = process_text(product_name)
        if len(display_name) > 35:
            display_name = display_name[:32] + "..."
        can.drawRightString(460, y_pos, display_name) 
        
        # 4. Qty
        can.drawCentredString(280, y_pos, str(qty))
        
        # 5. Unit Price
        can.drawCentredString(235, y_pos, f"{price:,.2f}")
        
        # 6. Total Excl
        can.drawCentredString(175, y_pos, f"{subtotal:,.2f}")
        
        # 7. VAT
        can.drawCentredString(115, y_pos, f"{tax:,.2f}")
        
        # 8. Total Incl (Far Left)
        can.drawCentredString(60, y_pos, f"{total_incl:,.2f}")
        
        can.setStrokeColorRGB(0.8, 0.8, 0.8)
        can.line(30, y_pos - 5, 565, y_pos - 5)
        can.setStrokeColorRGB(0, 0, 0)
        
        y_pos -= 20
        index_counter += 1
        
        # Increased bottom margin for footer
        if y_pos < 120:
            can.showPage()
            can.setFont(font_name, 9)
            y_pos = 700 # Restart higher on new pages? Or same. Let's do 700.
            # Redraw headers
            can.setFillColorRGB(0.9, 0.9, 0.9)
            can.rect(30, y_pos - 5, 535, 15, fill=1, stroke=0)
            can.setFillColorRGB(0, 0, 0)
            for x, title in headers:
                can.drawCentredString(x, y_pos, title)
            y_pos -= 25

    # Grand Total Section
    y_pos -= 30 # Increased spacing before Summary Table
    
    # Summary Table (Full Width)
    table_x = 30
    table_width = 535
    row_height = 20
    
    total_excl = invoice_df['Subtotal'].sum()
    total_tax = invoice_df['Tax (15%)'].sum()
    
    # 1. Total (Excluding VAT)
    draw_styled_row(y_pos, "Total (Excluding VAT)", f"SAR {total_excl:,.2f}", align_value_right=True)
    y_pos -= row_height
    
    # 2. Discount
    draw_styled_row(y_pos, "Discount", "SAR 0.00", align_value_right=True)
    y_pos -= row_height
    
    # 3. Total VAT
    draw_styled_row(y_pos, "Total VAT (15%)", f"SAR {total_tax:,.2f}", align_value_right=True)
    y_pos -= row_height
    
    # 4. Total Amount Due
    draw_styled_row(y_pos, "Total Amount Due", f"SAR {grand_total:,.2f}", is_bold=True, align_value_right=True)
    y_pos -= row_height
    
    can.save()
    
    # Merge
    packet.seek(0)
    new_pdf_layer = PdfReader(packet)
    existing_letterhead = PdfReader(letterhead_bytes)
    output = PdfWriter()

    if len(existing_letterhead.pages) > 0:
        page = existing_letterhead.pages[0]
        page.merge_page(new_pdf_layer.pages[0])
        output.add_page(page)
        
        for i in range(1, len(new_pdf_layer.pages)):
             if i < len(existing_letterhead.pages):
                 bg_page = existing_letterhead.pages[i]
             else:
                 bg_page = existing_letterhead.pages[0]
             
             bg_page.merge_page(new_pdf_layer.pages[i])
             output.add_page(bg_page)

        final_pdf = io.BytesIO()
        output.write(final_pdf)
        return final_pdf.getvalue()
    return None

# --- Main App ---
st.title("📄 Professional Invoice Generator")

# Initialize DB
init_db()

# Tabs
tab1, tab2 = st.tabs(["📝 Invoice Generator", "💾 Manage Data"])

with tab1:
    st.header("Create Invoice")
    
    # 1. Invoice Details
    st.subheader("Invoice Details")
    col1, col2 = st.columns(2)
    with col1:
        inv_date = st.date_input("Date")
        bill_no = st.text_input("Bill Number", value="1001")
        customer_name = st.text_input("Customer Name")
    with col2:
        customer_address = st.text_input("Customer Address")
        customer_vat = st.text_input("Customer VAT No.")
        payment_terms = st.text_input("Payment Method", value="Cash / Credit")

    st.divider()

    # 2. Select Letterhead
    letterhead_file = st.file_uploader("Upload Vendor Letterhead (PDF)", type=["pdf"], key="lh_uploader")
    
    # 3. Product Selection
    st.subheader("Select Products")
    
    db_products = load_products_from_db()
    
    if db_products.empty:
        st.warning("No products found in database. Go to 'Manage Data' tab to upload a price list.")
    else:
        if 'Quantity' not in db_products.columns:
            db_products['Quantity'] = 0
            
        edited_df = st.data_editor(
            db_products,
            column_config={
                "Product": st.column_config.TextColumn("Product Name", disabled=True),
                "Price": st.column_config.NumberColumn("Unit Price", format="SAR %.2f", disabled=True),
                "Quantity": st.column_config.NumberColumn("Quantity", min_value=0, step=1, format="%d")
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed" 
        )
        
        selected_items = edited_df[edited_df['Quantity'] > 0].copy()
        
        if not selected_items.empty:
            st.divider()
            st.subheader("Invoice Preview")
            
            selected_items['Subtotal'] = selected_items['Price'] * selected_items['Quantity']
            selected_items['Tax (15%)'] = selected_items['Subtotal'] * 0.15
            selected_items['Total'] = selected_items['Subtotal'] + selected_items['Tax (15%)']
            grand_total = selected_items['Total'].sum()
            
            st.dataframe(selected_items, use_container_width=True)
            st.metric("Grand Total", f"SAR {grand_total:,.2f}")
            
            if letterhead_file:
                if st.button("Generate PDF Invoice", type="primary"):
                    # Collect header info
                    header_info = {
                        "date": inv_date,
                        "bill_no": bill_no,
                        "customer": customer_name,
                        "address": customer_address,
                        "vat_no": customer_vat,
                        "terms": payment_terms
                    }
                    
                    pdf_bytes = generate_pdf(selected_items, letterhead_file, grand_total, header_info)
                    if pdf_bytes:
                        st.download_button(
                            label="⬇️ Download Final PDF",
                            data=pdf_bytes,
                            file_name=f"Invoice_{bill_no}.pdf",
                            mime="application/pdf"
                        )
                    else:
                        st.error("Failed to generate PDF.")
            else:
                st.info("Upload a Letterhead PDF above to enable generation.")
        else:
            st.info("Set Quantity > 0 for at least one item to see the preview.")


with tab2:
    st.header("Data Management")
    st.write("Upload a Master Price List to update the database.")
    
    upload_type = st.radio("Upload Format", ["Excel (.xlsx)", "PDF Price List (Item_Pricing.pdf)"])
    
    if upload_type == "Excel (.xlsx)":
        uploaded_master = st.file_uploader("Upload Excel", type=["xlsx"], key="excel_uploader")
        if uploaded_master and st.button("Update from Excel"):
            try:
                master_df = pd.read_excel(uploaded_master)
                success, msg = save_products_to_db(master_df)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            except Exception as e:
                st.error(f"Error reading file: {e}")
                
    else: # PDF
        uploaded_pdf = st.file_uploader("Upload Price List PDF", type=["pdf"], key="pdf_uploader")
        if uploaded_pdf and st.button("Update from PDF"):
            df, msg = parse_pricing_pdf_stream(uploaded_pdf)
            if df is not None:
                success, save_msg = save_products_to_db(df)
                if success:
                    st.success(f"Parsed {len(df)} items. {save_msg}")
                    st.rerun()
                else:
                    st.error(save_msg)
            else:
                st.error(msg)

    st.divider()
    st.subheader("Current Database Status")
    current_df = load_products_from_db()
    st.write(f"Total Products: {len(current_df)}")
    if not current_df.empty:
        st.dataframe(current_df, use_container_width=True)
    
    if st.button("Dangerous: Clear Database"):
        clear_db()
        st.rerun()
