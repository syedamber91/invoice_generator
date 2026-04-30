import streamlit as st
import pandas as pd

from quotation_pdf import generate_pdf

st.set_page_config(page_title="Oasis Quotation Builder", layout="wide", page_icon="📄")


# --- Custom CSS (Oasis theme) ---
st.markdown("""
<style>
    :root {
        --oasis-gold: #C9A961;
        --oasis-dark: #1a1a2e;
    }
    .stApp { background-color: #faf8f5; }
    .main-header {
        background: linear-gradient(135deg, #f5f0e8 0%, #ffffff 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        border: 2px solid #C9A961;
        border-left: 5px solid #C9A961;
        box-shadow: 0 4px 15px rgba(201, 169, 97, 0.2);
    }
    .main-header h1 { margin: 0; font-size: 1.8rem; color: #1a1a2e !important; font-weight: 700; }
    .main-header p { margin: 0.5rem 0 0 0; color: #333333 !important; }
    .step-box {
        background: #ffffff;
        border: 1px solid #C9A961;
        border-left: 5px solid #C9A961;
        padding: 0.8rem 1rem;
        margin-bottom: 1rem;
        border-radius: 8px;
    }
    .step-number {
        background: #ffffff;
        color: #000000;
        border: 2px solid #C9A961;
        padding: 2px 10px;
        border-radius: 50%;
        font-weight: bold;
        margin-right: 8px;
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
        background: #ffffff; color: #000000;
        border: 2px solid #C9A961; font-weight: 700;
    }
    h1, h2, h3, h4, h5, h6 { color: #000000 !important; }
    .stMarkdown, .stMarkdown p, p, span, label { color: #000000 !important; }
    .stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox > div > div, .stDateInput input {
        background-color: #ffffff !important; color: #000000 !important;
        border: 1px solid #C9A961 !important;
    }
    [data-testid="stFileUploader"] section {
        background-color: #fdfbf7 !important;
        border: 1px dashed #C9A961 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("""
<div class="main-header">
    <h1>🏨 Oasis Cotton Company - Quotation Builder</h1>
    <p>Generates professional quotations matching the Oasis house style</p>
</div>
""", unsafe_allow_html=True)


# ============ STEP 1: Quotation Reference & Customer ============
st.markdown('<div class="step-box"><span class="step-number">1</span><strong>Quotation Reference & Customer</strong></div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.caption("Reference info (left side of quotation)")
    ref = st.text_input("REF", value="AKT000300/00100-04", help="Internal reference number")
    q_ref = st.text_input("Q.Ref", value="300-04", help="Short quotation reference")
    date = st.date_input("Date")
    subject = st.text_input("Subject", value="Quotation for Linen Items")
    enquiry = st.text_input("Enquiry Type", value="PR - Whatsapp Enquiry", help="How the enquiry was received")

with c2:
    st.caption("Customer info")
    customer = st.text_input("TO (Customer)", value="", placeholder="e.g., AL KISWAH TOWER HOTEL MAKKAH")
    attn_name = st.text_input("Attn — Name", value="", placeholder="e.g., Mr. Wael Al Malki")
    attn_title = st.text_input("Attn — Title", value="", placeholder="e.g., Purchasing Manager")
    attn_mobile = st.text_input("Attn — Mobile", value="", placeholder="e.g., 059 619 9566")

st.divider()


# ============ STEP 2: Letterhead ============
st.markdown('<div class="step-box"><span class="step-number">2</span><strong>Upload Company Letterhead (PDF)</strong></div>', unsafe_allow_html=True)
letterhead_file = st.file_uploader("Letterhead PDF", type=["pdf"], key="lh")
if letterhead_file:
    st.success("✅ Letterhead uploaded")
else:
    st.info("Upload your letterhead PDF — the quotation will print on top of it.")

st.divider()


# ============ STEP 3: Items ============
st.markdown('<div class="step-box"><span class="step-number">3</span><strong>Add Items</strong></div>', unsafe_allow_html=True)
st.markdown('<div class="quick-tip">💡 Type product description, unit (e.g., pcs, roll), quantity and unit price. Click <strong>+</strong> at the bottom of the table to add a new row, or the trash icon to remove one. Total Price is calculated automatically.</div>', unsafe_allow_html=True)

if 'items_df' not in st.session_state:
    st.session_state.items_df = pd.DataFrame(
        [{"Product": "", "Unit": "pcs", "Quantity": 1, "Price": 0.0}]
    )

items_df = st.data_editor(
    st.session_state.items_df,
    column_config={
        "Product": st.column_config.TextColumn("Description", width="large", required=False),
        "Unit": st.column_config.TextColumn("Unit", width="small", default="pcs"),
        "Quantity": st.column_config.NumberColumn("Qty.", min_value=0, step=1, format="%d", width="small"),
        "Price": st.column_config.NumberColumn("Unit Price (SAR)", min_value=0.0, step=0.50, format="%.2f"),
    },
    hide_index=True,
    use_container_width=True,
    num_rows="dynamic",
    key="items_editor",
    height=320,
)

valid_items = items_df.copy()
valid_items = valid_items[
    valid_items['Product'].astype(str).str.strip().ne("") &
    (valid_items['Quantity'].fillna(0) > 0) &
    (valid_items['Price'].fillna(0) >= 0)
].copy()

# Live totals — show immediately below the items table
if not valid_items.empty:
    grand_total_excl = (valid_items['Quantity'] * valid_items['Price']).sum()
    vat_amount = grand_total_excl * 0.15
    net_amount = grand_total_excl + vat_amount
    s1, s2, s3, s4 = st.columns(4)
    with s1: st.metric("Items", len(valid_items))
    with s2: st.metric("Subtotal (Excl. VAT)", f"SAR {grand_total_excl:,.2f}")
    with s3: st.metric("VAT (15%)", f"SAR {vat_amount:,.2f}")
    with s4: st.metric("Net Total (Incl. VAT)", f"SAR {net_amount:,.2f}")

st.divider()


# ============ STEP 4: Footer & Bank Details ============
st.markdown('<div class="step-box"><span class="step-number">4</span><strong>Footer / Bank / Contact (printed at the bottom)</strong></div>', unsafe_allow_html=True)
st.caption("These rarely change — set once and forget. They appear at the end of every quotation.")

f1, f2 = st.columns(2)
with f1:
    delivery = st.text_input("Delivery", value="2 to 4 Days")
    payment_terms = st.text_input("Payment Terms", value="50% Advance 50% Upon Delivery")
    company_vat = st.text_input("Company VAT No.", value="3011 400 837 00 003")
    beneficiary = st.text_input("Beneficiary Name", value="Oasis Cotton Company")
with f2:
    bank_name = st.text_input("Bank Name", value="ALRAJHI BANK")
    account_no = st.text_input("A/C No. (IBAN)", value="SA9380000525608010314637")
    contact_name = st.text_input("Contact Name", value="ADIL MOHAMMED KHAN")
    contact_mobile = st.text_input("Contact Mobile", value="056 658 5168")
    contact_email = st.text_input("Contact Email", value="a.Khan@oasiscottoncompany.com")

st.divider()


# ============ Generate ============
if not valid_items.empty:
    if letterhead_file:
        if st.button("🚀 Generate PDF Quotation", type="primary"):
            header_info = {
                "ref": ref,
                "q_ref": q_ref,
                "date": date.strftime("%d/%m/%Y"),
                "subject": subject,
                "enquiry": enquiry,
                "customer": customer,
                "attn_name": attn_name,
                "attn_title": attn_title,
                "attn_mobile": attn_mobile,
                "delivery": delivery,
                "payment_terms": payment_terms,
                "company_vat": company_vat,
                "beneficiary": beneficiary,
                "bank_name": bank_name,
                "account_no": account_no,
                "contact_name": contact_name,
                "contact_mobile": contact_mobile,
                "contact_email": contact_email,
            }
            pdf_bytes = generate_pdf(valid_items, letterhead_file, header_info)
            if pdf_bytes:
                st.success("✅ PDF generated")
                st.download_button(
                    "📥 Download PDF",
                    data=pdf_bytes,
                    file_name=f"Quotation_{q_ref or ref}.pdf",
                    mime="application/pdf",
                )
            else:
                st.error("Failed to generate PDF.")
    else:
        st.warning("Upload a letterhead PDF (Step 2) to enable PDF generation.")
else:
    st.info("Add at least one item with a description, quantity and price to enable PDF generation.")
