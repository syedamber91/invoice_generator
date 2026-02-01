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

st.set_page_config(page_title="Oasis Cotton Company - Quotation Builder", layout="wide", page_icon="🏨")

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
    
    # --- Title: Quotation (Arabic) ---
    # Centered below letterhead
    title_text = process_text("عرض سعر")
    can.setFont(font_name, 14) # Smaller, standard weight
    can.drawCentredString(width / 2, 660, title_text)
    
    can.setFont(font_name, 10) # Reset
    
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
        
        # Border Color (Thin Grey)
        can.setStrokeColorRGB(0.7, 0.7, 0.7)
        can.setLineWidth(0.5)
        
        # Label Cell (Left) - Light Grey Background #F2F2F2 (approx 0.95)
        can.setFillColorRGB(0.95, 0.95, 0.95) 
        can.rect(table_x, y - row_height, label_w, row_height, stroke=1, fill=1)
        
        # Value Cell (Right) - White Background
        can.setFillColorRGB(1, 1, 1) 
        can.rect(table_x + label_w, y - row_height, value_w, row_height, stroke=1, fill=1)
        
        # Reset colors for Text
        can.setFillColorRGB(0, 0, 0) # Black Text
        can.setFont(font_name, 10 if not is_bold else 11)
        
        # Label Text (Left Aligned with padding)
        can.drawString(table_x + 5, y - 14, label)
        
        # Value Text Alignment Logic
        # Check if text is Arabic to force Right Alignment
        val_text = process_text(value)
        
        # Simple heuristic: Check if reshaped text has RTL characters or user forced right align
        # Since we reshaped it, checking for Arabic unicode block in original 'value' is safer
        # But 'align_value_right' flag overrides everything (used for numbers)
        
        is_arabic_text = any('\u0600' <= char <= '\u06FF' for char in str(value))
        
        if align_value_right or is_arabic_text:
             # Right align relative to the end of the value cell
             can.drawRightString(table_x + label_w + value_w - 5, y - 14, val_text)
        else:
             can.drawString(table_x + label_w + 5, y - 14, val_text)
        
        # Reset Line Width
        can.setLineWidth(1)
        can.setStrokeColorRGB(0, 0, 0)


    # --- Header Table ---
    can.setFont(font_name, 10)
    
    # 1. Date
    draw_styled_row(table_top, "Date", header_info['date'])
    table_top -= row_height
    
    # 2. Bill No
    draw_styled_row(table_top, "Quotation No", str(header_info['bill_no']))
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
    can.setFont(font_name, 9)
    # Header Background & Border
    can.setStrokeColorRGB(0.7, 0.7, 0.7)
    can.setLineWidth(0.5)
    can.setFillColorRGB(0.95, 0.95, 0.95) # #F2F2F2
    
    can.rect(30, y_pos - 5, 535, 15, fill=1, stroke=1)
    
    can.setFillColorRGB(0, 0, 0)
    can.setStrokeColorRGB(0, 0, 0) # Reset stroke for text/lines? Actually lines should be grey too?
    # Let's keep text black.
    
    for x, title in headers:
        can.drawCentredString(x, y_pos, title)
    
    # Reset for rows
    can.setLineWidth(1) # Or keep 0.5?
    pass
        
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
        
        # Row Separator (Thin Grey)
        can.setLineWidth(0.5)
        can.setStrokeColorRGB(0.7, 0.7, 0.7)
        can.line(30, y_pos - 5, 565, y_pos - 5)
        
        # Reset
        can.setLineWidth(1)
        can.setStrokeColorRGB(0, 0, 0)
        
        y_pos -= 20
        index_counter += 1
        
        # Increased bottom margin for footer
        if y_pos < 120:
            can.showPage()
            can.setFont(font_name, 9)
            y_pos = 700 # Restart higher on new pages? Or same. Let's do 700.
            # Redraw headers
            can.setStrokeColorRGB(0.7, 0.7, 0.7)
            can.setLineWidth(0.5)
            can.setFillColorRGB(0.95, 0.95, 0.95) # #F2F2F2
            
            can.rect(30, y_pos - 5, 535, 15, fill=1, stroke=1)
            
            can.setFillColorRGB(0, 0, 0)
            can.setStrokeColorRGB(0, 0, 0)
            
            for x, title in headers:
                can.drawCentredString(x, y_pos, title)
            
            can.setLineWidth(1)
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

# Custom CSS for better UI - Oasis Cotton Company Theme
st.markdown("""
<style>
    /* ===== Oasis Cotton Company Color Palette ===== */
    :root {
        --oasis-gold: #C9A961;
        --oasis-dark: #1a1a2e;
        --oasis-cream: #f5f0e8;
        --oasis-brown: #8B7355;
        --oasis-accent: #D4AF37;
    }
    
    /* ===== Global Streamlit Overrides ===== */
    .stApp {
        background-color: #faf8f5;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #2d2d44 100%);
        border-right: 3px solid #C9A961;
    }
    section[data-testid="stSidebar"] .stMarkdown {
        color: #f5f0e8;
    }
    section[data-testid="stSidebar"] label {
        color: #C9A961 !important;
    }
    section[data-testid="stSidebar"] .stTextInput input,
    section[data-testid="stSidebar"] .stNumberInput input {
        background-color: #2d2d44;
        color: #f5f0e8;
        border: 1px solid #C9A961;
    }
    section[data-testid="stSidebar"] .stSelectbox > div > div {
        background-color: #2d2d44;
        color: #f5f0e8;
    }
    
    /* Main header styling - Elegant dark with gold accent */
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #2d2d44 100%);
        padding: 1.2rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
        border-bottom: 4px solid #C9A961;
        box-shadow: 0 4px 15px rgba(26, 26, 46, 0.3);
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.6rem;
        color: #C9A961;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.9;
        color: #f5f0e8;
        font-size: 0.95rem;
    }
    
    /* Step indicator styling - Gold accent */
    .step-box {
        background: linear-gradient(135deg, #f5f0e8 0%, #fff 100%);
        border-left: 4px solid #C9A961;
        padding: 0.7rem 1rem;
        margin-bottom: 0.8rem;
        border-radius: 0 8px 8px 0;
        box-shadow: 0 2px 8px rgba(201, 169, 97, 0.15);
    }
    .step-number {
        background: linear-gradient(135deg, #C9A961 0%, #D4AF37 100%);
        color: #1a1a2e;
        padding: 3px 12px;
        border-radius: 15px;
        font-weight: bold;
        margin-right: 10px;
        font-size: 0.85rem;
    }
    
    /* Info card styling - Cream theme */
    .info-card {
        background: linear-gradient(135deg, #f5f0e8 0%, #fff 100%);
        border: 1px solid #C9A961;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        box-shadow: 0 2px 8px rgba(201, 169, 97, 0.1);
    }
    
    /* Quick tip styling */
    .quick-tip {
        background: linear-gradient(135deg, #fff9e6 0%, #fff3cd 100%);
        border: 1px solid #C9A961;
        padding: 0.7rem 1rem;
        border-radius: 8px;
        font-size: 0.9rem;
    }
    
    /* Sidebar header */
    .sidebar-header {
        background: linear-gradient(135deg, #C9A961 0%, #D4AF37 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        color: #1a1a2e;
        text-align: center;
        font-weight: bold;
    }
    
    /* Nav button in sidebar */
    .nav-button {
        background: rgba(201, 169, 97, 0.2);
        border: 1px solid #C9A961;
        padding: 0.8rem 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        cursor: pointer;
        transition: all 0.3s ease;
        color: #f5f0e8;
        text-align: left;
    }
    .nav-button:hover {
        background: rgba(201, 169, 97, 0.4);
    }
    .nav-button.active {
        background: #C9A961;
        color: #1a1a2e;
    }
    
    /* Success card */
    .success-card {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border: 1px solid #28a745;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    /* Streamlit button overrides */
    .stButton > button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #C9A961 0%, #D4AF37 100%) !important;
        color: #1a1a2e !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button[data-testid="baseButton-primary"]:hover {
        background: linear-gradient(135deg, #D4AF37 0%, #E5C158 100%) !important;
        box-shadow: 0 4px 12px rgba(201, 169, 97, 0.4) !important;
    }
    
    /* Metrics styling */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #fff 0%, #f5f0e8 100%);
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #C9A961;
        box-shadow: 0 2px 8px rgba(201, 169, 97, 0.1);
    }
    [data-testid="stMetricLabel"] {
        color: #1a1a2e !important;
    }
    [data-testid="stMetricValue"] {
        color: #C9A961 !important;
        font-weight: 700 !important;
    }
    
    /* Data editor styling */
    .stDataFrame {
        border: 1px solid #C9A961 !important;
        border-radius: 10px !important;
        overflow: hidden;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, #f5f0e8 0%, #fff 100%) !important;
        border: 1px solid #C9A961 !important;
        border-radius: 8px !important;
    }
    
    /* ===== Mobile Responsive ===== */
    @media (max-width: 768px) {
        .main-header {
            padding: 1rem;
        }
        .main-header h1 {
            font-size: 1.3rem;
        }
        .main-header p {
            font-size: 0.85rem;
        }
        .step-box {
            padding: 0.6rem 0.8rem;
        }
        .step-number {
            padding: 2px 8px;
            font-size: 0.8rem;
        }
        [data-testid="stMetric"] {
            padding: 0.7rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.2rem !important;
        }
    }
    
    @media (max-width: 480px) {
        .main-header h1 {
            font-size: 1.1rem;
        }
        section[data-testid="stSidebar"] {
            width: 100% !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# Initialize DB
init_db()

# ============================================
# SIDEBAR - Navigation & Product Management
# ============================================
with st.sidebar:
    # Company branding header
    st.markdown("""
    <div class="sidebar-header">
        <h3 style="margin:0; font-size:1.1rem;">🏨 Oasis Cotton Co.</h3>
        <p style="margin:0.3rem 0 0 0; font-size:0.8rem; opacity:0.9;">Quotation Builder</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Navigation
    st.markdown("##### 📍 Navigation")
    st.info("📝 **Quotation Generator** - Create & manage quotations")
    
    st.divider()
    
    # Current status
    current_df = load_products_from_db()
    st.metric("📦 Products in Database", len(current_df))
    
    st.divider()
    
    # --- Add New Product ---
    st.markdown("##### ➕ Add New Product")
    new_product_name = st.text_input(
        "Product Name", 
        key="new_product_name", 
        placeholder="e.g., Cotton Roll 100m",
        label_visibility="collapsed"
    )
    new_product_price = st.number_input(
        "Price (SAR)", 
        min_value=0.0, 
        step=0.50, 
        format="%.2f", 
        key="new_product_price"
    )
    if st.button("➕ Add Product", key="add_product_btn", use_container_width=True, type="primary"):
        if new_product_name.strip():
            new_row = pd.DataFrame([{'Product': new_product_name.strip(), 'Price': new_product_price}])
            success, msg = save_products_to_db(new_row)
            if success:
                st.success(f"✅ Added!")
                st.rerun()
            else:
                st.error(f"❌ {msg}")
        else:
            st.warning("Enter a name")
    
    st.divider()
    
    # --- Edit Products (Expander) ---
    with st.expander("✏️ Edit Products", expanded=False):
        if not current_df.empty:
            st.caption("Double-click to edit, check 🗑️ to delete")
            
            edit_df = current_df.copy()
            edit_df.insert(0, 'Delete', False)
            
            edited_products = st.data_editor(
                edit_df,
                column_config={
                    "Delete": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
                    "Product": st.column_config.TextColumn("Product", width="medium"),
                    "Price": st.column_config.NumberColumn("SAR", format="%.2f", width="small"),
                },
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
                key="product_editor",
                height=250
            )
            
            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                to_delete = edited_products[edited_products['Delete'] == True]['Product'].tolist()
                to_update = edited_products[edited_products['Delete'] == False][['Product', 'Price']]
                
                if to_delete:
                    conn = init_db()
                    c = conn.cursor()
                    for product_name in to_delete:
                        c.execute("DELETE FROM products WHERE name = ?", (product_name,))
                    conn.commit()
                    conn.close()
                
                if not to_update.empty:
                    clear_db()
                    success, msg = save_products_to_db(to_update)
                    if success:
                        st.success(f"✅ Saved!")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
                elif to_delete:
                    st.success(f"✅ Deleted!")
                    st.rerun()
        else:
            st.info("No products yet")
    
    # --- Import from File (Expander) ---
    with st.expander("📤 Import from File", expanded=False):
        upload_type = st.radio(
            "File type:", 
            ["Excel", "PDF"],
            key="upload_format",
            horizontal=True
        )
        
        if upload_type == "Excel":
            uploaded_master = st.file_uploader("Upload Excel", type=["xlsx"], key="excel_uploader", label_visibility="collapsed")
            if uploaded_master:
                if st.button("📥 Import Excel", type="primary", use_container_width=True):
                    try:
                        with st.spinner("Importing..."):
                            master_df = pd.read_excel(uploaded_master)
                            success, msg = save_products_to_db(master_df)
                            if success:
                                st.success("✅ Imported!")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                    except Exception as e:
                        st.error(f"❌ {e}")
        else:
            uploaded_pdf = st.file_uploader("Upload PDF", type=["pdf"], key="pdf_uploader", label_visibility="collapsed")
            if uploaded_pdf:
                if st.button("📥 Import PDF", type="primary", use_container_width=True):
                    with st.spinner("Parsing..."):
                        df, msg = parse_pricing_pdf_stream(uploaded_pdf)
                        if df is not None:
                            success, save_msg = save_products_to_db(df)
                            if success:
                                st.success(f"✅ Imported {len(df)} items!")
                                st.rerun()
                            else:
                                st.error(f"❌ {save_msg}")
                        else:
                            st.error(f"❌ {msg}")
    
    st.divider()
    
    # --- Danger Zone ---
    with st.expander("⚠️ Clear Database", expanded=False):
        st.error("⚠️ This cannot be undone!")
        if st.button("🗑️ Clear ALL", type="secondary", use_container_width=True):
            clear_db()
            st.success("Cleared!")
            st.rerun()

# ============================================
# MAIN CONTENT - Quotation Builder
# ============================================

# Main Header
st.markdown("""
<div class="main-header">
    <h1>🏨 Oasis Cotton Company - Quotation Builder</h1>
    <p>Create professional quotations with automatic VAT calculation and PDF generation</p>
</div>
""", unsafe_allow_html=True)

# Load product count for display
product_count = len(load_products_from_db())

# Quick status bar
col_status1, col_status2, col_status3 = st.columns(3)
with col_status1:
    st.metric("📦 Products Available", product_count)
with col_status2:
    st.metric("💰 VAT Rate", "15%")
with col_status3:
    st.metric("💵 Currency", "SAR")

st.divider()

# Step 1: Customer Details
st.markdown("""
<div class="step-box">
    <span class="step-number">1</span>
    <strong>Enter Customer & Quotation Details</strong>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    date = st.date_input("📅 Quotation Date", help="Date of the quotation")
    bill_no = st.text_input("🔢 Quotation Number", value="1001", help="Unique quotation reference number")
    customer_name = st.text_input("👤 Customer Name", placeholder="Enter customer name...", help="Name of the customer")
with col2:
    customer_address = st.text_input("📍 Customer Address", placeholder="Enter address...", help="Customer's address")
    customer_vat = st.text_input("🏢 Customer VAT No.", placeholder="e.g., 300000000000003", help="Customer's VAT registration number")
    payment_terms = st.text_input("💳 Payment Method", value="Cash / Credit", help="Payment terms or method")

st.divider()

# Step 2: Upload Letterhead
st.markdown("""
<div class="step-box">
    <span class="step-number">2</span>
    <strong>Upload Your Company Letterhead</strong>
</div>
""", unsafe_allow_html=True)

letterhead_file = st.file_uploader(
    "📎 Upload Letterhead PDF", 
    type=["pdf"], 
    key="lh_uploader",
    help="Upload your company's letterhead PDF. The quotation will be generated on top of this."
)

if not letterhead_file:
    st.info("💡 **Tip:** Upload your company letterhead to generate professional branded quotations.")
else:
    st.success("✅ Letterhead uploaded!")

st.divider()

# Step 3: Product Selection
st.markdown("""
<div class="step-box">
    <span class="step-number">3</span>
    <strong>Select Products & Set Quantities</strong>
</div>
""", unsafe_allow_html=True)

db_products = load_products_from_db()

if db_products.empty:
    st.warning("⚠️ **No products in database!** Use the sidebar (⚙️ Product Management) to add products.")
    st.markdown("""
    <div class="info-card">
        <strong>🚀 Quick Start:</strong><br>
        1. Look at the <strong>sidebar on the left</strong> (⚙️ Product Management)<br>
        2. Add products manually OR import from Excel/PDF<br>
        3. Then select products here to build your quotation
    </div>
    """, unsafe_allow_html=True)
else:
    st.caption(f"📦 **{len(db_products)} products available** — Set quantity > 0 to add items to your quotation")
    
    if 'Quantity' not in db_products.columns:
        db_products['Quantity'] = 0
        
    edited_df = st.data_editor(
        db_products,
        column_config={
            "Product": st.column_config.TextColumn("📦 Product Name", disabled=True, width="large"),
            "Price": st.column_config.NumberColumn("💰 Unit Price (SAR)", format="%.2f", disabled=True),
            "Quantity": st.column_config.NumberColumn("🔢 Qty", min_value=0, step=1, format="%d", width="small")
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        height=350
    )
    
    selected_items = edited_df[edited_df['Quantity'] > 0].copy()
    
    if not selected_items.empty:
        st.divider()
        
        # Step 4: Review & Generate
        st.markdown("""
        <div class="step-box">
            <span class="step-number">4</span>
            <strong>Review & Generate Quotation</strong>
        </div>
        """, unsafe_allow_html=True)
        
        # Calculate totals
        selected_items['Subtotal'] = selected_items['Price'] * selected_items['Quantity']
        selected_items['Tax (15%)'] = selected_items['Subtotal'] * 0.15
        selected_items['Total'] = selected_items['Subtotal'] + selected_items['Tax (15%)']
        grand_total = selected_items['Total'].sum()
        subtotal_sum = selected_items['Subtotal'].sum()
        tax_sum = selected_items['Tax (15%)'].sum()
        
        # Summary metrics
        st.markdown("### 📋 Quotation Summary")
        
        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
        with sum_col1:
            st.metric("📦 Items", len(selected_items))
        with sum_col2:
            st.metric("💵 Subtotal", f"SAR {subtotal_sum:,.2f}")
        with sum_col3:
            st.metric("🏛️ VAT (15%)", f"SAR {tax_sum:,.2f}")
        with sum_col4:
            st.metric("💰 Grand Total", f"SAR {grand_total:,.2f}")
        
        # Detailed preview
        with st.expander("📊 View Detailed Breakdown", expanded=True):
            st.dataframe(
                selected_items[['Product', 'Price', 'Quantity', 'Subtotal', 'Tax (15%)', 'Total']],
                use_container_width=True,
                column_config={
                    "Product": st.column_config.TextColumn("Product"),
                    "Price": st.column_config.NumberColumn("Unit Price", format="SAR %.2f"),
                    "Quantity": st.column_config.NumberColumn("Qty", format="%d"),
                    "Subtotal": st.column_config.NumberColumn("Subtotal", format="SAR %.2f"),
                    "Tax (15%)": st.column_config.NumberColumn("VAT", format="SAR %.2f"),
                    "Total": st.column_config.NumberColumn("Total", format="SAR %.2f"),
                }
            )
        
        st.divider()
        
        # Generate button
        if letterhead_file:
            gen_col1, gen_col2 = st.columns([1, 3])
            with gen_col1:
                if st.button("🚀 Generate PDF Quotation", type="primary", use_container_width=True):
                    with st.spinner("Generating your quotation..."):
                        header_info = {
                            "date": str(date),
                            "bill_no": bill_no,
                            "customer": customer_name,
                            "address": customer_address,
                            "vat_no": customer_vat,
                            "terms": payment_terms
                        }
                        
                        pdf_bytes = generate_pdf(selected_items, letterhead_file, grand_total, header_info)
                        
                        if pdf_bytes:
                            st.success("✅ PDF Generated Successfully!")
                            st.download_button(
                                label="📥 Download PDF Quotation",
                                data=pdf_bytes,
                                file_name=f"Quotation_{bill_no}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                        else:
                            st.error("❌ Failed to generate PDF. Please check your inputs.")
        else:
            st.warning("⚠️ **Upload a letterhead PDF** (Step 2) to enable PDF generation.")
    else:
        st.markdown("""
        <div class="quick-tip">
            💡 <strong>How to add items:</strong> Set the <strong>Qty</strong> column to any number greater than 0 for products you want to include in your quotation.
        </div>
        """, unsafe_allow_html=True)
