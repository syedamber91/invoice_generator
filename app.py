import streamlit as st
import pandas as pd
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
# Use a font that supports Arabic. Arial usually does on Mac/Windows.
FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"  # Mac common
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "Arial.ttf"  # Fallback to local if user provides it

st.set_page_config(page_title="Dynamic Quotation Builder", layout="wide", page_icon="📄")


# --- PDF Generation Logic ---
def generate_pdf(invoice_df, letterhead_bytes, grand_total, header_info):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    width, height = A4

    # Register Arabic Font
    try:
        pdfmetrics.registerFont(TTFont('ArabicFont', FONT_PATH))
        font_name = 'ArabicFont'
    except Exception:
        st.error(f"Could not load font from {FONT_PATH}. Using default.")
        font_name = 'Helvetica'

    def process_text(text):
        if font_name == 'ArabicFont':
            reshaped_text = arabic_reshaper.reshape(str(text))
            bidi_text = get_display(reshaped_text)
            return bidi_text
        return str(text)

    can.setFont(font_name, 10)

    # --- Title: Quotation (Arabic) ---
    title_text = process_text("عرض سعر")
    can.setFont(font_name, 14)
    can.drawCentredString(width / 2, 660, title_text)

    can.setFont(font_name, 10)

    # Coordinates
    table_top = 620
    row_height = 20

    # Table bounds
    table_x = 300
    table_width = 265

    def draw_styled_row(y, label, value, is_bold=False, align_value_right=False):
        label_width_pct = 0.35
        label_w = table_width * label_width_pct
        value_w = table_width * (1 - label_width_pct)

        can.setStrokeColorRGB(0.7, 0.7, 0.7)
        can.setLineWidth(0.5)

        can.setFillColorRGB(0.95, 0.95, 0.95)
        can.rect(table_x, y - row_height, label_w, row_height, stroke=1, fill=1)

        can.setFillColorRGB(1, 1, 1)
        can.rect(table_x + label_w, y - row_height, value_w, row_height, stroke=1, fill=1)

        can.setFillColorRGB(0, 0, 0)
        can.setFont(font_name, 10 if not is_bold else 11)

        can.drawString(table_x + 5, y - 14, label)

        val_text = process_text(value)
        is_arabic_text = any('؀' <= char <= 'ۿ' for char in str(value))

        if align_value_right or is_arabic_text:
            can.drawRightString(table_x + label_w + value_w - 5, y - 14, val_text)
        else:
            can.drawString(table_x + label_w + 5, y - 14, val_text)

        can.setLineWidth(1)
        can.setStrokeColorRGB(0, 0, 0)

    # --- Header Table ---
    can.setFont(font_name, 10)

    draw_styled_row(table_top, "Date", header_info['date'])
    table_top -= row_height

    draw_styled_row(table_top, "Quotation No", str(header_info['bill_no']))
    table_top -= row_height

    draw_styled_row(table_top, "Customer", header_info['customer'])
    table_top -= row_height

    draw_styled_row(table_top, "Address", header_info['address'])
    table_top -= row_height

    draw_styled_row(table_top, "VAT Number", header_info['vat_no'])
    table_top -= row_height

    draw_styled_row(table_top, "Payment Method", header_info['terms'])
    table_top -= row_height

    # --- Item Table Header ---
    y_pos = table_top - 60

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
    can.setStrokeColorRGB(0.7, 0.7, 0.7)
    can.setLineWidth(0.5)
    can.setFillColorRGB(0.95, 0.95, 0.95)

    can.rect(30, y_pos - 5, 535, 15, fill=1, stroke=1)

    can.setFillColorRGB(0, 0, 0)
    can.setStrokeColorRGB(0, 0, 0)

    for x, title in headers:
        can.drawCentredString(x, y_pos, title)

    can.setLineWidth(1)
    y_pos -= 25

    # Item Rows
    can.setFont(font_name, 9)
    index_counter = 1

    for index, row in invoice_df.iterrows():
        product_name = row['Product']
        item_code = ""

        code_match = re.match(r'^(\d+)\s+(.+)', product_name)
        if code_match:
            item_code = code_match.group(1)
            product_name = code_match.group(2)

        qty = row['Quantity']
        price = row['Price']
        subtotal = row['Subtotal']
        tax = row['Tax (15%)']
        total_incl = row['Total']

        can.drawCentredString(550, y_pos, str(index_counter))
        can.drawCentredString(500, y_pos, item_code)

        display_name = process_text(product_name)
        if len(display_name) > 35:
            display_name = display_name[:32] + "..."
        can.drawRightString(460, y_pos, display_name)

        can.drawCentredString(280, y_pos, str(qty))
        can.drawCentredString(235, y_pos, f"{price:,.2f}")
        can.drawCentredString(175, y_pos, f"{subtotal:,.2f}")
        can.drawCentredString(115, y_pos, f"{tax:,.2f}")
        can.drawCentredString(60, y_pos, f"{total_incl:,.2f}")

        can.setLineWidth(0.5)
        can.setStrokeColorRGB(0.7, 0.7, 0.7)
        can.line(30, y_pos - 5, 565, y_pos - 5)

        can.setLineWidth(1)
        can.setStrokeColorRGB(0, 0, 0)

        y_pos -= 20
        index_counter += 1

        if y_pos < 120:
            can.showPage()
            can.setFont(font_name, 9)
            y_pos = 700
            can.setStrokeColorRGB(0.7, 0.7, 0.7)
            can.setLineWidth(0.5)
            can.setFillColorRGB(0.95, 0.95, 0.95)

            can.rect(30, y_pos - 5, 535, 15, fill=1, stroke=1)

            can.setFillColorRGB(0, 0, 0)
            can.setStrokeColorRGB(0, 0, 0)

            for x, title in headers:
                can.drawCentredString(x, y_pos, title)

            can.setLineWidth(1)
            y_pos -= 25

    # Grand Total Section
    y_pos -= 30

    table_x = 30
    table_width = 535
    row_height = 20

    total_excl = invoice_df['Subtotal'].sum()
    total_tax = invoice_df['Tax (15%)'].sum()

    draw_styled_row(y_pos, "Total (Excluding VAT)", f"SAR {total_excl:,.2f}", align_value_right=True)
    y_pos -= row_height

    draw_styled_row(y_pos, "Discount", "SAR 0.00", align_value_right=True)
    y_pos -= row_height

    draw_styled_row(y_pos, "Total VAT (15%)", f"SAR {total_tax:,.2f}", align_value_right=True)
    y_pos -= row_height

    draw_styled_row(y_pos, "Total Amount Due", f"SAR {grand_total:,.2f}", is_bold=True, align_value_right=True)
    y_pos -= row_height

    # --- Footer block: Validity, Payment Terms, Beneficiary, Bank, IBAN ---
    footer_fields = [
        ("Validity of Quotation", header_info.get('validity', '')),
        ("Payment Terms", header_info.get('payment_terms', '')),
        ("Beneficiary Name", header_info.get('beneficiary', '')),
        ("Bank Name", header_info.get('bank_name', '')),
        ("IBAN Number", header_info.get('iban', '')),
    ]

    # Need ~ (5 rows + header gap) ≈ 130pt of space; new page if not enough
    if y_pos - (len(footer_fields) * row_height + 30) < 60:
        can.showPage()
        # Page break: fall back to a known top position for the footer
        y_pos = 700

    y_pos -= 20  # spacing between totals and footer block

    can.setFont(font_name, 11)
    can.setFillColorRGB(0, 0, 0)
    can.drawString(table_x, y_pos, "Quotation Terms & Bank Details")
    y_pos -= 8
    can.setStrokeColorRGB(0.7, 0.7, 0.7)
    can.setLineWidth(0.5)
    can.line(table_x, y_pos, table_x + table_width, y_pos)
    y_pos -= 6
    can.setFont(font_name, 10)

    for label, value in footer_fields:
        draw_styled_row(y_pos, label, value if value else "—")
        y_pos -= row_height

    can.save()

    # Merge with letterhead
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

# Custom CSS - Oasis Cotton Company Theme
st.markdown("""
<style>
    :root {
        --oasis-gold: #C9A961;
        --oasis-dark: #1a1a2e;
        --oasis-cream: #f5f0e8;
        --oasis-accent: #D4AF37;
    }

    .stApp {
        background-color: #faf8f5;
    }

    section[data-testid="stSidebar"] {
        background: #f8f9fa !important;
        border-right: 3px solid #C9A961;
    }
    section[data-testid="stSidebar"] * {
        color: #1a1a2e !important;
    }
    section[data-testid="stSidebar"] .stTextInput input,
    section[data-testid="stSidebar"] .stNumberInput input {
        background-color: #ffffff;
        color: #1a1a2e;
        border: 1px solid #C9A961;
    }

    .main-header {
        background: linear-gradient(135deg, #f5f0e8 0%, #ffffff 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        border: 2px solid #C9A961;
        border-left: 5px solid #C9A961;
        box-shadow: 0 4px 15px rgba(201, 169, 97, 0.2);
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.8rem;
        color: #1a1a2e !important;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        color: #333333 !important;
    }

    .step-box {
        background: #ffffff;
        border: 1px solid #C9A961;
        border-left: 5px solid #C9A961;
        padding: 0.8rem 1rem;
        margin-bottom: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(201, 169, 97, 0.1);
    }
    .step-number {
        background: #ffffff;
        color: #000000;
        border: 2px solid #C9A961;
        padding: 2px 10px;
        border-radius: 50%;
        font-weight: bold;
        margin-right: 8px;
        display: inline-block;
    }

    .info-card {
        background: #ffffff;
        border: 1px solid #C9A961;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }

    .quick-tip {
        background: #ffffff;
        border: 1px solid #C9A961;
        padding: 0.7rem 1rem;
        border-radius: 8px;
        font-size: 0.9rem;
        color: #000000;
    }

    .stButton > button[data-testid="baseButton-primary"] {
        background: #ffffff;
        color: #000000;
        border: 2px solid #C9A961;
        font-weight: 700;
    }
    .stButton > button[data-testid="baseButton-primary"]:hover {
        background: #fdfbf7;
        border-color: #D4AF37;
        color: #000000;
        box-shadow: 0 2px 5px rgba(201, 169, 97, 0.2);
    }

    [data-testid="stMetricValue"] {
        color: #000000 !important;
        font-weight: 700;
    }

    h1, h2, h3, h4, h5, h6,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        color: #000000 !important;
    }
    .stMarkdown, .stMarkdown p, p, span, label {
        color: #000000 !important;
    }
    .stExpander summary, .stExpander p {
        color: #000000 !important;
    }

    .stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox > div > div, .stDateInput input {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #C9A961 !important;
    }
    ul[data-testid="stSelectboxVirtualList"] li {
        background-color: #ffffff !important;
        color: #000000 !important;
    }

    [data-testid="stDataFrame"], [data-testid="stTable"], [data-testid="stDataEditor"], .stDataFrame, .stDataEditor {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #C9A961 !important;
    }
    [data-testid="stDataFrame"] div[role="columnheader"],
    div[data-testid="stDataFrame"] div[class*="header"] {
        background-color: #ffffff !important;
        color: #000000 !important;
        border-bottom: 2px solid #C9A961 !important;
        border-right: 1px solid #e0d2b4 !important;
        font-weight: 700 !important;
    }
    [data-testid="stDataFrame"] div[role="gridcell"],
    div[data-testid="stDataFrame"] div[class*="cell"] {
        color: #000000 !important;
        background-color: #ffffff !important;
        border-bottom: 1px solid #e0d2b4 !important;
        border-right: 1px solid #e0d2b4 !important;
    }
    [data-testid="stDataFrame"] div[role="row"] {
        background-color: #ffffff !important;
        color: #000000 !important;
        border-bottom: 1px solid #e0d2b4 !important;
    }
    .glide-data-grid {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #C9A961 !important;
    }

    [data-testid="stFileUploader"] {
        background-color: #ffffff !important;
        color: #000000 !important;
    }
    [data-testid="stFileUploader"] section {
        background-color: #fdfbf7 !important;
        border: 1px dashed #C9A961 !important;
        color: #000000 !important;
    }
    [data-testid="stFileUploader"] section:hover {
        background-color: #fff9e6 !important;
        border-color: #D4AF37 !important;
    }
    [data-testid="stFileUploader"] span,
    [data-testid="stFileUploader"] small,
    [data-testid="stFileUploader"] p {
        color: #000000 !important;
    }
</style>
""", unsafe_allow_html=True)

# Main Header
st.markdown("""
<div class="main-header">
    <h1>🏨 Oasis Cotton Company - Quotation Builder</h1>
    <p>Create professional quotations with automatic VAT calculation and PDF generation</p>
</div>
""", unsafe_allow_html=True)

# Quick status bar
col_status1, col_status2 = st.columns(2)
with col_status1:
    st.metric("💰 VAT Rate", "15%")
with col_status2:
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
    payment_method = st.text_input("💳 Payment Method", value="Cash / Credit", help="How payment will be made (e.g., Cash, Credit, Bank Transfer)")

st.markdown("##### 📜 Quotation Terms & Bank Details")
st.caption("These appear at the end of the generated quotation PDF.")

term_col1, term_col2 = st.columns(2)
with term_col1:
    validity = st.text_input("⏳ Validity of Quotation", value="30 days from quotation date", help="How long this quotation remains valid")
    payment_terms = st.text_input("📑 Payment Terms", value="50% advance, 50% on delivery", help="Payment terms (e.g., Net 30, 50% advance)")
    beneficiary = st.text_input("👥 Beneficiary Name", placeholder="e.g., Oasis Cotton Company", help="Name of the bank account holder")
with term_col2:
    bank_name = st.text_input("🏦 Bank Name", placeholder="e.g., Al Rajhi Bank", help="Bank where payment should be sent")
    iban = st.text_input("🔢 IBAN Number", placeholder="e.g., SA00 0000 0000 0000 0000 0000", help="International Bank Account Number")

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
    st.success("✅ Letterhead uploaded successfully!")

st.divider()

# Step 3: Add Products Manually
st.markdown("""
<div class="step-box">
    <span class="step-number">3</span>
    <strong>Add Products to the Quotation</strong>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="quick-tip">
    💡 <strong>How to add items:</strong> Type the product name, unit price, and quantity in each row.
    Click the <strong>+</strong> at the bottom of the table to add another row. Click the trash icon to remove a row.
</div>
""", unsafe_allow_html=True)

# Initialise an empty editable table for manual product entry
if 'products_df' not in st.session_state:
    st.session_state.products_df = pd.DataFrame(
        [{"Product": "", "Price": 0.0, "Quantity": 1}]
    )

products_df = st.data_editor(
    st.session_state.products_df,
    column_config={
        "Product": st.column_config.TextColumn(
            "📦 Product Name",
            help="Type the product name",
            width="large",
            required=True,
        ),
        "Price": st.column_config.NumberColumn(
            "💰 Unit Price (SAR)",
            help="Unit price in SAR",
            min_value=0.0,
            step=0.50,
            format="%.2f",
        ),
        "Quantity": st.column_config.NumberColumn(
            "🔢 Qty",
            help="Quantity",
            min_value=0,
            step=1,
            format="%d",
            width="small",
        ),
    },
    hide_index=True,
    use_container_width=True,
    num_rows="dynamic",
    key="product_entry_editor",
    height=400,
)

# Filter to only valid rows (have a product name and a positive quantity)
selected_items = products_df.copy()
selected_items = selected_items[
    selected_items['Product'].astype(str).str.strip().ne("") &
    (selected_items['Quantity'].fillna(0) > 0) &
    (selected_items['Price'].fillna(0) >= 0)
].copy()

if not selected_items.empty:
    st.divider()

    # Step 4: Review & Generate
    st.markdown("""
    <div class="step-box">
        <span class="step-number">4</span>
        <strong>Review & Generate Quotation</strong>
    </div>
    """, unsafe_allow_html=True)

    selected_items['Subtotal'] = selected_items['Price'] * selected_items['Quantity']
    selected_items['Tax (15%)'] = selected_items['Subtotal'] * 0.15
    selected_items['Total'] = selected_items['Subtotal'] + selected_items['Tax (15%)']
    grand_total = selected_items['Total'].sum()
    subtotal_sum = selected_items['Subtotal'].sum()
    tax_sum = selected_items['Tax (15%)'].sum()

    st.markdown("### 📋 Quotation Summary")

    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    with sum_col1:
        st.metric("📦 Items", len(selected_items))
    with sum_col2:
        st.metric("💵 Subtotal", f"SAR {subtotal_sum:,.2f}")
    with sum_col3:
        st.metric("🏛️ VAT (15%)", f"SAR {tax_sum:,.2f}")
    with sum_col4:
        st.metric("💰 Grand Total", f"SAR {grand_total:,.2f}", delta=None)

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
            },
        )

    st.divider()

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
                        "terms": payment_method,
                        "validity": validity,
                        "payment_terms": payment_terms,
                        "beneficiary": beneficiary,
                        "bank_name": bank_name,
                        "iban": iban,
                    }

                    pdf_bytes = generate_pdf(selected_items, letterhead_file, grand_total, header_info)

                    if pdf_bytes:
                        st.success("✅ PDF Generated Successfully!")
                        st.download_button(
                            label="📥 Download PDF Quotation",
                            data=pdf_bytes,
                            file_name=f"Quotation_{bill_no}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                    else:
                        st.error("❌ Failed to generate PDF. Please check your inputs.")
    else:
        st.warning("⚠️ **Upload a letterhead PDF** (Step 2) to enable PDF generation.")
else:
    st.markdown("""
    <div class="quick-tip">
        💡 Add at least one product with a name, unit price, and a quantity greater than 0 to see the summary and generate the PDF.
    </div>
    """, unsafe_allow_html=True)
