from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter
import io
import os

import arabic_reshaper
from bidi.algorithm import get_display

FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "Arial.ttf"



def generate_pdf(items_df, letterhead_bytes, header_info):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    width, height = A4

    try:
        pdfmetrics.registerFont(TTFont('ArabicFont', FONT_PATH))
        font_name = 'ArabicFont'
    except Exception:
        font_name = 'Helvetica'

    def shape(text):
        if font_name == 'ArabicFont':
            return get_display(arabic_reshaper.reshape(str(text)))
        return str(text)

    # Colors
    RED = (0.90, 0.05, 0.10)
    GREY_BG = (0.94, 0.94, 0.94)
    GREY_BORDER = (0.65, 0.65, 0.65)
    BLACK = (0, 0, 0)

    def set_fill(rgb):
        can.setFillColorRGB(*rgb)

    def set_stroke(rgb):
        can.setStrokeColorRGB(*rgb)

    def cell(x, y, w, h, label, value, label_w_ratio=0.35,
             value_color=BLACK, label_bg=GREY_BG, value_bg=(1, 1, 1),
             font_size=9, value_bold=False, value_align="left"):
        """Draw a single styled cell with label box on left and value box on right."""
        label_w = w * label_w_ratio
        value_w = w - label_w

        set_stroke(GREY_BORDER)
        can.setLineWidth(0.5)

        # Label cell
        set_fill(label_bg)
        can.rect(x, y - h, label_w, h, stroke=1, fill=1)
        # Value cell
        set_fill(value_bg)
        can.rect(x + label_w, y - h, value_w, h, stroke=1, fill=1)

        # Label text
        set_fill(BLACK)
        can.setFont(font_name, font_size)
        can.drawString(x + 4, y - h + 4, label)

        # Value text (may be empty)
        set_fill(value_color)
        can.setFont(font_name, font_size + (1 if value_bold else 0))
        v = shape(value)
        if value_align == "right":
            can.drawRightString(x + label_w + value_w - 4, y - h + 4, v)
        elif value_align == "center":
            can.drawCentredString(x + label_w + value_w / 2, y - h + 4, v)
        else:
            can.drawString(x + label_w + 4, y - h + 4, v)

    def empty_cell(x, y, w, h, fill=(1, 1, 1)):
        set_stroke(GREY_BORDER)
        can.setLineWidth(0.5)
        set_fill(fill)
        can.rect(x, y - h, w, h, stroke=1, fill=1)

    # ============ TOP REFERENCE GRID ============
    top_y = 640
    row_h = 18
    left_x, left_w = 30, 250
    right_x, right_w = 305, 260

    # Left column: REF / TO / Attn / [Title] / Mob / Subject (6 rows)
    rows_left = [
        ("REF", header_info.get("ref", ""), RED),
        ("TO", header_info.get("customer", ""), BLACK),
        ("Attn", header_info.get("attn_name", ""), BLACK),
        ("", header_info.get("attn_title", ""), BLACK),
        ("Mob", header_info.get("attn_mobile", ""), BLACK),
        ("Subject", header_info.get("subject", ""), BLACK),
    ]

    y = top_y
    for label, value, color in rows_left:
        cell(left_x, y, left_w, row_h, label, value, value_color=color, value_bold=(color == RED))
        y -= row_h

    # Right column header: "QUOTATION" red bold title spanning full right block
    y = top_y
    set_stroke(GREY_BORDER)
    can.setLineWidth(0.5)
    set_fill((1, 1, 1))
    can.rect(right_x, y - row_h, right_w, row_h, stroke=1, fill=1)
    set_fill(RED)
    can.setFont('Helvetica-Bold', 16)
    can.drawCentredString(right_x + right_w / 2, y - row_h + 5, "QUOTATION")
    y -= row_h

    # Then Q.Ref / Enquiry / Date
    rows_right = [
        ("Q.Ref", header_info.get("q_ref", "")),
        ("", header_info.get("enquiry", "")),
        ("Date", header_info.get("date", "")),
    ]
    for label, value in rows_right:
        cell(right_x, y, right_w, row_h, label, value)
        y -= row_h
    # Pad remaining rows on right side with empty cells to match left height
    while y > top_y - 6 * row_h:
        empty_cell(right_x, y, right_w, row_h)
        y -= row_h

    # ============ ITEMS TABLE ============
    items_y = top_y - 6 * row_h - 14

    # Column widths (sum = 535)
    cols = [
        ("S. #", 35, "center"),
        ("Description", 215, "left"),
        ("Unit", 55, "center"),
        ("Qty.", 55, "center"),
        ("Unit Price", 80, "right"),
        ("Total Price", 95, "right"),
    ]
    table_x_start = 30
    table_total_w = sum(c[1] for c in cols)

    def draw_items_header(y):
        set_stroke(GREY_BORDER)
        can.setLineWidth(0.5)
        set_fill(GREY_BG)
        can.rect(table_x_start, y - row_h, table_total_w, row_h, stroke=1, fill=1)
        set_fill(BLACK)
        can.setFont(font_name, 10)
        cx = table_x_start
        for title, w, _ in cols:
            can.drawCentredString(cx + w / 2, y - row_h + 5, title)
            can.line(cx, y, cx, y - row_h)
            cx += w
        can.line(cx, y, cx, y - row_h)
        return y - row_h

    items_y = draw_items_header(items_y)

    # Item rows — render exactly the rows in the dataframe (don't pad)
    # Bottom-of-page guard: leave room above the letterhead's footer
    PAGE_BOTTOM_GUARD = 100
    can.setFont(font_name, 9)
    for i, row in enumerate(items_df.itertuples(index=False), start=1):
        if items_y - row_h < PAGE_BOTTOM_GUARD:
            can.showPage()
            items_y = 760  # top of next page (clear of letterhead header)
            items_y = draw_items_header(items_y)
            can.setFont(font_name, 9)

        cx = table_x_start
        # white row
        set_fill((1, 1, 1))
        can.rect(table_x_start, items_y - row_h, table_total_w, row_h, stroke=1, fill=1)
        set_fill(BLACK)

        unit = getattr(row, 'Unit', '') or ''
        desc = shape(getattr(row, 'Product', ''))
        qty = getattr(row, 'Quantity', 0) or 0
        price = float(getattr(row, 'Price', 0) or 0)
        total = qty * price

        values = [
            (str(i), "center"),
            (desc, "left"),
            (str(unit), "center"),
            (str(qty), "center"),
            (f"{price:,.2f}", "right"),
            (f"{total:,.2f}", "right"),
        ]
        for (val, align), (_, w, _) in zip(values, cols):
            if align == "left":
                can.drawString(cx + 4, items_y - row_h + 5, val)
            elif align == "right":
                can.drawRightString(cx + w - 4, items_y - row_h + 5, val)
            else:
                can.drawCentredString(cx + w / 2, items_y - row_h + 5, val)
            can.line(cx, items_y, cx, items_y - row_h)
            cx += w
        can.line(cx, items_y, cx, items_y - row_h)

        items_y -= row_h

    # If totals + footer (~210pt) won't fit below the items, break to a new page
    TOTALS_FOOTER_RESERVE = 210
    if items_y - TOTALS_FOOTER_RESERVE < 60:
        can.showPage()
        items_y = 760

    # ============ TOTALS ============
    grand_total_excl = (items_df['Quantity'] * items_df['Price']).sum()
    vat_amount = grand_total_excl * 0.15
    net_amount = grand_total_excl + vat_amount

    totals_y = items_y - 6
    company_vat = header_info.get("company_vat", "")

    # Row 1: "Grand Total : SAR Only." | amount
    cell(table_x_start, totals_y, table_total_w, row_h,
         "Grand  Total : SAR Only.", f"{grand_total_excl:,.2f}",
         label_w_ratio=0.78, font_size=10, value_bold=True, value_align="right")
    totals_y -= row_h
    # Row 2: company VAT no.  +  "Add V.A.T 15%" label and amount
    set_stroke(GREY_BORDER)
    can.setLineWidth(0.5)
    set_fill((1, 1, 1))
    # Three sub-cells: company VAT (left), "Add V.A.T 15%" middle, value right
    sub_w_a = 200
    sub_w_b = table_total_w * 0.78 - sub_w_a
    sub_w_c = table_total_w * 0.22
    can.rect(table_x_start, totals_y - row_h, sub_w_a, row_h, stroke=1, fill=1)
    set_fill(GREY_BG)
    can.rect(table_x_start + sub_w_a, totals_y - row_h, sub_w_b, row_h, stroke=1, fill=1)
    set_fill((1, 1, 1))
    can.rect(table_x_start + sub_w_a + sub_w_b, totals_y - row_h, sub_w_c, row_h, stroke=1, fill=1)
    set_fill(BLACK)
    can.setFont(font_name, 10)
    can.drawString(table_x_start + 4, totals_y - row_h + 4, company_vat)
    can.drawCentredString(table_x_start + sub_w_a + sub_w_b / 2, totals_y - row_h + 4, "Add   V.A.T 15%")
    can.drawRightString(table_x_start + table_total_w - 4, totals_y - row_h + 4, f"{vat_amount:,.2f}")
    totals_y -= row_h
    # Row 3: Net Amount including 15% VAT | net amount
    cell(table_x_start, totals_y, table_total_w, row_h,
         "Net Amount including 15% VAT", f"{net_amount:,.2f}",
         label_w_ratio=0.78, font_size=10, value_bold=True, value_align="right")
    totals_y -= row_h

    # ============ FOOTER (left-aligned text block) ============
    footer_y = totals_y - 22
    can.setFont(font_name, 10)

    def line(x, txt, color=BLACK, bold=False, size=10):
        set_fill(color)
        can.setFont(font_name, size + (1 if bold else 0))
        can.drawString(x, footer_y_local[0], shape(txt))

    footer_y_local = [footer_y]

    def write_line(txt, color=BLACK, bold=False, gap=14, x=30):
        set_fill(color)
        can.setFont(font_name, 10 + (1 if bold else 0))
        can.drawString(x, footer_y_local[0], shape(txt))
        footer_y_local[0] -= gap

    delivery = header_info.get("delivery", "")
    beneficiary = header_info.get("beneficiary", "")
    payment_terms = header_info.get("payment_terms", "")
    bank_name = header_info.get("bank_name", "")
    account_no = header_info.get("account_no", "")
    contact_name = header_info.get("contact_name", "")
    contact_mobile = header_info.get("contact_mobile", "")
    contact_email = header_info.get("contact_email", "")

    write_line(f"*** DELIVERY : {delivery}", color=RED, bold=True)
    write_line(f"Name   {beneficiary}")
    footer_y_local[0] -= 4
    write_line(f"Payment Terms: {payment_terms}", color=RED)
    write_line(f"Bank Details:   {bank_name}", color=RED)
    write_line(f"A/C No.   {account_no}")
    footer_y_local[0] -= 4
    write_line("THANKS & BEST REGARDS", bold=True)
    contact_line = contact_name
    if contact_mobile:
        contact_line = f"{contact_name} - {contact_mobile}"
    write_line(contact_line)
    write_line(f"Email: {contact_email}")

    can.save()

    # Merge with letterhead if provided
    packet.seek(0)
    new_pdf_layer = PdfReader(packet)

    if letterhead_bytes is not None:
        # Read raw letterhead bytes once so we can re-parse fresh for each page
        if hasattr(letterhead_bytes, 'read'):
            letterhead_bytes.seek(0)
            raw = letterhead_bytes.read()
        else:
            raw = letterhead_bytes
        # Probe to count letterhead pages
        probe = PdfReader(io.BytesIO(raw))
        n_letterhead_pages = len(probe.pages)
        if n_letterhead_pages == 0:
            return None

        output = PdfWriter()
        for i in range(len(new_pdf_layer.pages)):
            # Re-parse the letterhead each time so merge_page mutates a fresh page
            fresh = PdfReader(io.BytesIO(raw))
            bg_idx = i if i < n_letterhead_pages else 0
            bg_page = fresh.pages[bg_idx]
            bg_page.merge_page(new_pdf_layer.pages[i])
            output.add_page(bg_page)

        final = io.BytesIO()
        output.write(final)
        return final.getvalue()

    # No letterhead — return the layer as-is
    return packet.getvalue()

