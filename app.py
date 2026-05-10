import streamlit as st
import pandas as pd
from datetime import date as _date

from quotation_pdf import generate_pdf, fmt_money
from storage import get_storage

st.set_page_config(
    page_title="Oasis Quotation Builder",
    layout="wide",
    page_icon="📄",
    initial_sidebar_state="collapsed",
)


# ============================================================================
# Session state defaults — every form field has a key so it can be loaded from
# a draft or an archived quotation by simply writing to st.session_state.
# ============================================================================
EMPTY_ITEMS = pd.DataFrame([{"Product": "", "Quantity": 1, "Price": 0.0}])

DEFAULTS = {
    "ref": "AKT000300/00100-04",
    "q_ref": "300-04",
    "date": _date.today(),
    "subject": "Quotation for Linen Items",
    "enquiry": "PR - Whatsapp Enquiry",
    "customer": "",
    "attn_name": "",
    "attn_title": "",
    "attn_mobile": "",
    "delivery": "2 to 4 Days",
    "validity": "30 Days",
    "payment_terms": "50% Advance 50% Upon Delivery",
    "company_vat": "3011 400 837 00 003",
    "beneficiary": "Oasis Cotton Company",
    "bank_name": "ALRAJHI BANK",
    "account_no": "SA9380000525608010314637",
    "contact_name": "ADIL MOHAMMED KHAN",
    "contact_mobile": "056 658 5168",
    "contact_email": "a.Khan@oasiscottoncompany.com",
    "items_df": EMPTY_ITEMS.copy(),
    # meta
    "draft_name": "",
}

for _k, _v in DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ----------------------------------------------------------------------------
# Helpers — collect form into a payload and apply a payload back into widgets.
# ----------------------------------------------------------------------------
PAYLOAD_FIELDS = [
    "ref", "q_ref", "date", "subject", "enquiry",
    "customer", "attn_name", "attn_title", "attn_mobile",
    "delivery", "validity", "payment_terms", "company_vat",
    "beneficiary", "bank_name", "account_no",
    "contact_name", "contact_mobile", "contact_email",
]


def collect_payload(items_df: pd.DataFrame) -> dict:
    """Snapshot the current form (header fields + items) into a JSON-safe dict."""
    payload: dict = {f: st.session_state.get(f, "") for f in PAYLOAD_FIELDS}
    # Date as ISO string — JSON-safe and easy to parse back
    d = payload.get("date")
    if hasattr(d, "isoformat"):
        payload["date"] = d.isoformat()
    payload["items"] = items_df.to_dict("records") if items_df is not None else []
    return payload


def apply_payload(payload: dict) -> None:
    """Push a loaded payload into session_state so widgets repopulate on rerun."""
    for f in PAYLOAD_FIELDS:
        if f in payload:
            val = payload[f]
            if f == "date" and isinstance(val, str):
                try:
                    val = _date.fromisoformat(val)
                except ValueError:
                    val = _date.today()
            st.session_state[f] = val
    items = payload.get("items") or []
    df = pd.DataFrame(items) if items else EMPTY_ITEMS.copy()
    # Streamlit data_editor caches edit deltas under its own key — clear them
    # so the new DataFrame shows through cleanly.
    st.session_state["items_df"] = df
    st.session_state.pop("items_editor", None)


storage = get_storage()


# ============================================================================
# Custom CSS (Oasis theme)
# ============================================================================
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
    section[data-testid="stSidebar"] { background: #f8f9fa !important; border-right: 3px solid #C9A961; }
    section[data-testid="stSidebar"] * { color: #1a1a2e !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# SIDEBAR (top half) — Load draft + Browse archive
# Save draft button is rendered later (in the second `with st.sidebar:` block)
# so it can capture the current items DataFrame returned by the data_editor.
# ============================================================================
with st.sidebar:
    backend_label = "☁️ Turso" if storage.backend == "turso" else "💾 Local SQLite"
    st.caption(f"Storage backend: {backend_label}")

    # ---- Drafts: load / delete ----
    st.markdown("### 📂 Drafts")
    drafts = storage.list_drafts()
    if drafts:
        opts = [-1] + [d["id"] for d in drafts]

        def _fmt_draft(idx_id: int) -> str:
            if idx_id == -1:
                return "— select a draft —"
            d = next(x for x in drafts if x["id"] == idx_id)
            return f"{d['name']}  ({d['updated_at'][:10]})"

        picked_id = st.selectbox(
            "Load saved draft",
            options=opts,
            format_func=_fmt_draft,
            key="draft_picker",
            label_visibility="collapsed",
        )
        if picked_id != -1:
            cl1, cl2 = st.columns(2)
            with cl1:
                if st.button("📂 Load", key="btn_load_draft", use_container_width=True):
                    loaded = storage.load_draft(int(picked_id))
                    if loaded:
                        apply_payload(loaded["payload"])
                        st.session_state["draft_name"] = loaded["name"]
                        st.toast(f"Loaded draft: {loaded['name']}")
                        st.rerun()
            with cl2:
                if st.button("🗑️ Delete", key="btn_del_draft", use_container_width=True):
                    storage.delete_draft(int(picked_id))
                    st.toast("Draft deleted")
                    st.rerun()
    else:
        st.caption("No drafts saved yet. Fill the form, then save below.")

    st.divider()

    # ---- Archive: browse / download / duplicate / delete ----
    st.markdown("### 📚 Archive (generated PDFs)")
    archives = storage.list_archive()
    if archives:
        a_opts = [-1] + [a["id"] for a in archives]

        def _fmt_arch(idx_id: int) -> str:
            if idx_id == -1:
                return "— select a quotation —"
            a = next(x for x in archives if x["id"] == idx_id)
            ref = a["ref"] or a["q_ref"] or f"#{a['id']}"
            cust = a["customer"] or "(no customer)"
            return f"{ref} · {cust}  ({a['created_at'][:10]})"

        picked_arch_id = st.selectbox(
            "Pick an archived quotation",
            options=a_opts,
            format_func=_fmt_arch,
            key="archive_picker",
            label_visibility="collapsed",
        )
        if picked_arch_id != -1:
            full = storage.load_archive(int(picked_arch_id))
            if full:
                fname = (full["ref"] or full["q_ref"] or f"quotation_{picked_arch_id}").replace("/", "-")
                st.download_button(
                    "📥 Download PDF",
                    data=full["pdf_bytes"],
                    file_name=f"Quotation_{fname}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_archive_{picked_arch_id}",
                )
                ad1, ad2 = st.columns(2)
                with ad1:
                    if st.button("📂 Load", key="btn_dup_arch", use_container_width=True,
                                 help="Load this quotation into the editor as a new working copy"):
                        apply_payload(full["payload"])
                        st.toast("Loaded into editor")
                        st.rerun()
                with ad2:
                    if st.button("🗑️ Delete", key="btn_del_arch", use_container_width=True):
                        storage.delete_archive(int(picked_arch_id))
                        st.toast("Archive entry deleted")
                        st.rerun()
    else:
        st.caption("No PDFs archived yet. They'll appear here after you click Generate.")


# ============================================================================
# MAIN — header
# ============================================================================
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
    st.text_input("REF", key="ref", help="Internal reference number")
    st.text_input("Q.Ref", key="q_ref", help="Short quotation reference")
    st.date_input("Date", key="date")
    st.text_input("Subject", key="subject")
    st.text_input("Enquiry Type", key="enquiry", help="How the enquiry was received")

with c2:
    st.caption("Customer info")
    st.text_input("TO (Customer)", key="customer", placeholder="e.g., AL KISWAH TOWER HOTEL MAKKAH")
    st.text_input("Attn — Name", key="attn_name", placeholder="e.g., Mr. Wael Al Malki")
    st.text_input("Attn — Title", key="attn_title", placeholder="e.g., Purchasing Manager")
    st.text_input("Attn — Mobile", key="attn_mobile", placeholder="e.g., 059 619 9566")

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
st.markdown('<div class="quick-tip">💡 Type product description, quantity and unit price. Click <strong>+</strong> at the bottom of the table to add a new row, or the trash icon to remove one. Total Price is calculated automatically.</div>', unsafe_allow_html=True)

items_df = st.data_editor(
    st.session_state["items_df"],
    column_config={
        "Product": st.column_config.TextColumn("Description", width="large", required=False),
        "Quantity": st.column_config.NumberColumn("Qty.", min_value=0, step=1, format="%d", width="small"),
        "Price": st.column_config.NumberColumn("Unit Price (SAR)", min_value=0.0, step=0.01, format="%.2f"),
    },
    hide_index=True,
    use_container_width=True,
    num_rows="dynamic",
    key="items_editor",
    height=320,
)
# Don't write items_df back into session_state["items_df"] here — the editor
# stores edits as a delta against its input, so mutating the input on every
# rerun causes cell values to drop. session_state["items_df"] is only updated
# when we explicitly want to reset the rows (apply_payload on draft load).

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
    with s2: st.metric("Subtotal (Excl. VAT)", f"SAR {fmt_money(grand_total_excl)}")
    with s3: st.metric("VAT (15%)", f"SAR {fmt_money(vat_amount)}")
    with s4: st.metric("Net Total (Incl. VAT)", f"SAR {fmt_money(net_amount)}")

st.divider()


# ============ STEP 4: Footer & Bank Details ============
st.markdown('<div class="step-box"><span class="step-number">4</span><strong>Footer / Bank / Contact (printed at the bottom)</strong></div>', unsafe_allow_html=True)
st.caption("These rarely change — set once and forget. They appear at the end of every quotation.")

f1, f2 = st.columns(2)
with f1:
    st.text_input("Delivery", key="delivery")
    st.text_input("Validity of Quotation", key="validity")
    st.text_input("Payment Terms", key="payment_terms")
    st.text_input("Company VAT No.", key="company_vat")
    st.text_input("Beneficiary Name", key="beneficiary")
with f2:
    st.text_input("Bank Name", key="bank_name")
    st.text_input("IBAN", key="account_no")
    st.text_input("Contact Name", key="contact_name")
    st.text_input("Contact Mobile", key="contact_mobile")
    st.text_input("Contact Email", key="contact_email")

st.divider()


# ============================================================================
# SIDEBAR (bottom half) — Save current as draft
# Rendered after the form so it captures the freshest items_df.
# ============================================================================
with st.sidebar:
    st.divider()
    st.markdown("### 💾 Save current as draft")
    st.text_input(
        "Draft name",
        key="draft_name",
        placeholder="e.g., AL KISWAH v2",
        label_visibility="collapsed",
    )
    if st.button("💾 Save draft", type="primary", use_container_width=True, key="btn_save_draft"):
        name = st.session_state.get("draft_name", "").strip()
        if not name:
            st.warning("Enter a draft name first.")
        else:
            payload = collect_payload(items_df)
            storage.save_draft(name, payload)
            st.toast(f"Saved draft: {name}")
            st.rerun()


# ============================================================================
# Generate PDF — also writes the rendered PDF + payload to the archive
# ============================================================================
def _build_header_info(payload: dict) -> dict:
    """Convert a saved payload into the kwargs generate_pdf expects.

    Only difference: date is formatted DD/MM/YYYY for the printed header."""
    d = payload.get("date")
    if isinstance(d, str):
        try:
            d = _date.fromisoformat(d)
        except ValueError:
            d = _date.today()
    elif d is None:
        d = _date.today()
    out = {f: payload.get(f, "") for f in PAYLOAD_FIELDS}
    out["date"] = d.strftime("%d/%m/%Y")
    return out


if not valid_items.empty:
    if letterhead_file:
        if st.button("🚀 Generate PDF Quotation", type="primary"):
            payload = collect_payload(valid_items)
            header_info = _build_header_info(payload)
            pdf_bytes = generate_pdf(valid_items, letterhead_file, header_info)
            if pdf_bytes:
                # Persist the rendered PDF and the form snapshot so it can be
                # retrieved later from the Archive panel in the sidebar.
                storage.archive_pdf(
                    ref=payload.get("ref", ""),
                    q_ref=payload.get("q_ref", ""),
                    customer=payload.get("customer", ""),
                    payload=payload,
                    pdf_bytes=pdf_bytes,
                )
                st.success("✅ PDF generated and saved to Archive")
                fname = (payload.get("q_ref") or payload.get("ref") or "Quotation").replace("/", "-")
                st.download_button(
                    "📥 Download PDF",
                    data=pdf_bytes,
                    file_name=f"Quotation_{fname}.pdf",
                    mime="application/pdf",
                )
            else:
                st.error("Failed to generate PDF.")
    else:
        st.warning("Upload a letterhead PDF (Step 2) to enable PDF generation.")
else:
    st.info("Add at least one item with a description, quantity and price to enable PDF generation.")
