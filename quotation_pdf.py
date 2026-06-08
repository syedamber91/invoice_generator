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


def fmt_money(value):
    """Format money as a thousands-separated value with exactly 2 decimals."""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _probe_top_letterhead_zone(letterhead_bytes, page_height, default=170, padding=22):
    """Find how far down the letterhead's top band extends and reserve enough
    space above it so drawn content doesn't overlap the logo.

    Returns the height (in PDF points) to reserve at the top of every page.
    Falls back to ``default`` if the letterhead can't be probed.
    """
    if not letterhead_bytes:
        return default
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return default
    try:
        doc = fitz.open(stream=letterhead_bytes, filetype="pdf")
        page = doc[0]
        # Header band: element must START in the top ~25% AND not extend more
        # than ~30% down the page. That filters out large body / background
        # images that happen to begin near the top but span the whole page.
        start_max = 200.0   # absolute pt from top
        end_max = 260.0
        lowest = 0.0
        for img in page.get_images(full=True):
            for r in page.get_image_rects(img[0]):
                if r.y0 < start_max and r.y1 < end_max:
                    lowest = max(lowest, r.y1)
        for blk in page.get_text("blocks"):
            y0, y1 = blk[1], blk[3]
            if y0 < start_max and y1 < end_max:
                lowest = max(lowest, y1)
        for d in page.get_drawings():
            r = d.get("rect")
            if r is not None and r.y0 < start_max and r.y1 < end_max:
                lowest = max(lowest, r.y1)
        if lowest <= 0:
            return default
        # Convert "from-top" Y back to a top-reserve height, plus padding.
        zone = lowest + padding
        # Clamp so we never reserve less than a sensible floor or more than
        # half the page.
        return max(120, min(zone, page_height * 0.5))
    except Exception:
        return default


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

    from reportlab.pdfbase.pdfmetrics import stringWidth

    def wrap_to_width(text, font, size, max_w, padding=8):
        """Greedy word-wrap: returns lines that fit within max_w (minus padding)."""
        avail = max_w - padding
        if not text:
            return [""]
        words = str(text).split(' ')
        lines, current = [], ""
        for word in words:
            candidate = (current + " " + word).strip() if current else word
            if stringWidth(candidate, font, size) <= avail:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                # Hard-break very long single words
                while stringWidth(current, font, size) > avail and len(current) > 1:
                    cut = len(current)
                    while cut > 1 and stringWidth(current[:cut], font, size) > avail:
                        cut -= 1
                    lines.append(current[:cut])
                    current = current[cut:]
        if current:
            lines.append(current)
        return lines or [""]

    # ============ TOP REFERENCE GRID ============
    # Single column box on the LEFT side of the page (bill-style layout).
    # The right side stays empty so the letterhead PDF underneath shows
    # through there.
    # TOP_LETTERHEAD_ZONE: pixels reserved at the top of every page for the
    # letterhead's header band. Probed from the uploaded letterhead so the
    # gap auto-adjusts to whatever logo the user supplies; falls back to a
    # safe constant if probing fails.
    PAGE_HEIGHT = 842  # A4 in points
    TOP_LETTERHEAD_ZONE = _probe_top_letterhead_zone(
        letterhead_bytes, PAGE_HEIGHT, default=170
    )
    top_y = PAGE_HEIGHT - TOP_LETTERHEAD_ZONE
    CONTINUATION_PAGE_TOP_Y = top_y
    row_h = 18
    box_x, box_w = 30, 260

    # "QUOTATION" title (red bold) at the top of the box
    y = top_y
    set_stroke(GREY_BORDER)
    can.setLineWidth(0.5)
    set_fill((1, 1, 1))
    can.rect(box_x, y - row_h, box_w, row_h, stroke=1, fill=1)
    set_fill(RED)
    can.setFont('Helvetica-Bold', 16)
    can.drawCentredString(box_x + box_w / 2, y - row_h + 5, "QUOTATION")
    y -= row_h

    # Field order requested by user:
    # Q.Ref → Date → Customer Name → Address → VAT # → CR # → Contact → Number
    rows = [
        ("Q.Ref",          header_info.get("q_ref", ""),            BLACK),
        ("Date",           header_info.get("date", ""),             BLACK),
        ("Customer Name",  header_info.get("customer", ""),         BLACK),
        ("Address",        header_info.get("customer_address", ""), BLACK),
        ("VAT #",          header_info.get("customer_vat", ""),     BLACK),
        ("CR #",           header_info.get("customer_cr", ""),      BLACK),
        ("Contact Person", header_info.get("attn_name", ""),        BLACK),
        ("Contact #",      header_info.get("attn_mobile", ""),      BLACK),
    ]
    # Word-wrap any overflowing value so long fields (e.g. Address) stay
    # inside the value column instead of bleeding past the right edge.
    label_w_ratio = 0.35
    label_w = box_w * label_w_ratio
    value_w = box_w - label_w
    line_h_hdr = 11
    for label, value, color in rows:
        v_shaped = shape(value)
        lines = wrap_to_width(v_shaped, font_name, 9, value_w)
        n = max(1, len(lines))
        this_row_h = max(row_h, line_h_hdr * n + 6)

        set_stroke(GREY_BORDER)
        can.setLineWidth(0.5)
        set_fill(GREY_BG)
        can.rect(box_x, y - this_row_h, label_w, this_row_h, stroke=1, fill=1)
        set_fill((1, 1, 1))
        can.rect(box_x + label_w, y - this_row_h, value_w, this_row_h, stroke=1, fill=1)

        # Label baseline aligned with the first (top) value line so multi-line
        # rows read naturally with the label at the top.
        set_fill(BLACK)
        can.setFont(font_name, 9)
        first_baseline = y - this_row_h + 4 + (n - 1) * line_h_hdr
        can.drawString(box_x + 4, first_baseline, label)

        set_fill(color)
        can.setFont(font_name, 9 + (1 if color == RED else 0))
        for i, ln in enumerate(lines):
            baseline = y - this_row_h + 4 + (n - 1 - i) * line_h_hdr
            can.drawString(box_x + label_w + 4, baseline, ln)

        y -= this_row_h

    header_box_bottom = y  # bottom edge of the header box, used to position items below

    # ============ ITEMS TABLE ============
    items_y = header_box_bottom - 8

    # Column widths (sum = 535) — 6 columns, Item code between S.# and Description
    cols = [
        ("S. #", 30, "center"),
        ("Item", 70, "center"),
        ("Description", 245, "left"),
        ("Qty.", 60, "center"),
        ("Unit Price", 60, "right"),
        ("Total Price", 70, "right"),
    ]
    table_x_start = 30
    table_total_w = sum(c[1] for c in cols)
    desc_w = cols[2][1]
    line_h = 11  # per-line height for wrapped text

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

    # Item rows
    # BOTTOM_LETTERHEAD_ZONE: pixels reserved at the bottom of every page
    # for the letterhead's bottom band (address line + QR code). Nothing
    # the script draws — items, totals, footer text — may extend below
    # this line, otherwise it covers the QR/address content underneath.
    BOTTOM_LETTERHEAD_ZONE = 130
    PAGE_BOTTOM_GUARD = BOTTOM_LETTERHEAD_ZONE
    can.setFont(font_name, 9)
    for i, row in enumerate(items_df.itertuples(index=False), start=1):
        desc = shape(getattr(row, 'Product', ''))
        qty = getattr(row, 'Quantity', 0) or 0
        price = float(getattr(row, 'Price', 0) or 0)
        total = qty * price

        # Wrap both Item code and Description; row height grows to fit the
        # taller of the two (or the default row_h, whichever is largest).
        item_code = str(getattr(row, 'Item', '') or '')
        item_lines = wrap_to_width(item_code, font_name, 9, cols[1][1])
        desc_lines = wrap_to_width(desc, font_name, 9, desc_w)
        max_lines = max(len(item_lines), len(desc_lines))
        row_h_actual = max(row_h, line_h * max_lines + 6)

        # Page break check using the *actual* row height. We pack items
        # greedily — every item that physically fits goes on the current
        # page, filling it up to the letterhead's bottom QR band. The
        # totals + footer overflow to the next page on their own (handled
        # by the separate check below the loop) only when they don't fit
        # below the last item.
        if items_y - row_h_actual < PAGE_BOTTOM_GUARD:
            can.showPage()
            items_y = CONTINUATION_PAGE_TOP_Y
            items_y = draw_items_header(items_y)
            can.setFont(font_name, 9)

        # White row background
        set_fill((1, 1, 1))
        can.rect(table_x_start, items_y - row_h_actual, table_total_w, row_h_actual, stroke=1, fill=1)
        set_fill(BLACK)

        cx = table_x_start
        first_baseline = items_y - line_h - 1  # first line baseline near top of row

        # S. # — vertically centered
        sw = cols[0][1]
        can.drawCentredString(cx + sw / 2, items_y - row_h_actual / 2 - 2, str(i))
        can.line(cx, items_y, cx, items_y - row_h_actual)
        cx += sw

        # Item code — top-aligned, wrapped, each line horizontally centered
        # (matches Description wrap behaviour so long codes don't overflow
        # into the next column).
        iw = cols[1][1]
        for li, ln in enumerate(item_lines):
            can.drawCentredString(cx + iw / 2, first_baseline - li * line_h, ln)
        can.line(cx, items_y, cx, items_y - row_h_actual)
        cx += iw

        # Description — top-aligned, wrapped
        dw = cols[2][1]
        for li, ln in enumerate(desc_lines):
            can.drawString(cx + 4, first_baseline - li * line_h, ln)
        can.line(cx, items_y, cx, items_y - row_h_actual)
        cx += dw

        # Qty. — thousands-separated
        qw = cols[3][1]
        try:
            qty_text = f"{int(qty):,}"
        except (TypeError, ValueError):
            qty_text = str(qty)
        can.drawCentredString(cx + qw / 2, items_y - row_h_actual / 2 - 2, qty_text)
        can.line(cx, items_y, cx, items_y - row_h_actual)
        cx += qw

        # Unit Price
        upw = cols[4][1]
        can.drawRightString(cx + upw - 4, items_y - row_h_actual / 2 - 2, fmt_money(price))
        can.line(cx, items_y, cx, items_y - row_h_actual)
        cx += upw

        # Total Price
        tpw = cols[5][1]
        can.drawRightString(cx + tpw - 4, items_y - row_h_actual / 2 - 2, fmt_money(total))
        can.line(cx, items_y, cx, items_y - row_h_actual)
        cx += tpw
        can.line(cx, items_y, cx, items_y - row_h_actual)

        items_y -= row_h_actual

    # Two-stage overflow handling:
    # 1. If the totals table alone (2pt items-gap + 3 × 18pt = 56pt) won't fit
    #    on this page, break here so the totals AND the footer both land on
    #    page 2.
    # 2. Otherwise draw totals here (glued under the last item), then check
    #    below — after the totals are drawn — whether the footer text block
    #    fits. If not, the footer alone moves to page 2.
    TOTALS_TABLE_HEIGHT = 56  # 2pt items-gap + 3 totals rows × 18pt
    if items_y - TOTALS_TABLE_HEIGHT < BOTTOM_LETTERHEAD_ZONE:
        can.showPage()
        items_y = CONTINUATION_PAGE_TOP_Y

    # ============ TOTALS ============
    grand_total_excl = (items_df['Quantity'] * items_df['Price']).sum()
    vat_amount = grand_total_excl * 0.15
    net_amount = grand_total_excl + vat_amount

    totals_y = items_y - 2
    company_vat = header_info.get("company_vat", "")

    # Row 1: "Grand Total : SAR Only." | amount
    cell(table_x_start, totals_y, table_total_w, row_h,
         "Grand  Total : SAR Only.", fmt_money(grand_total_excl),
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
    can.drawRightString(table_x_start + table_total_w - 4, totals_y - row_h + 4, fmt_money(vat_amount))
    totals_y -= row_h
    # Row 3: Net Amount including 15% VAT | net amount
    cell(table_x_start, totals_y, table_total_w, row_h,
         "Net Amount including 15% VAT", fmt_money(net_amount),
         label_w_ratio=0.78, font_size=10, value_bold=True, value_align="right")
    totals_y -= row_h

    # If the footer text block won't fit above the letterhead's bottom band,
    # move just the footer to a fresh page. The totals stay where they were
    # drawn (glued under the last item on the previous page).
    # Footer block height: 14pt lead-in + last text baseline at 130pt below
    # footer_y (8 × 14pt + 4pt + 14pt mid-gap) + ~3pt descender = ~133pt of
    # actual ink. Reserve 138 to leave ~5pt safety above BOTTOM_LETTERHEAD_ZONE.
    FOOTER_BLOCK_HEIGHT = 138
    if totals_y - FOOTER_BLOCK_HEIGHT < BOTTOM_LETTERHEAD_ZONE:
        can.showPage()
        totals_y = CONTINUATION_PAGE_TOP_Y

    # ============ FOOTER (left-aligned text block) ============
    # 14pt lead-in below the totals table — tight enough that 8 items + totals
    # + footer fit on page 1, loose enough that the footer still reads as a
    # separate block from the totals.
    footer_y = totals_y - 14
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
    validity = header_info.get("validity", "")

    write_line(f"*** DELIVERY : {delivery}", color=RED, bold=True)
    write_line(f"Validity of Quotation : {validity}", color=RED, bold=True)
    write_line(f"Name   {beneficiary}")
    footer_y_local[0] -= 4
    write_line(f"Payment Terms: {payment_terms}", color=RED)
    write_line(f"Bank Details:   {bank_name}", color=RED)
    write_line(f"IBAN   {account_no}")
    footer_y_local[0] -= 14  # blank space between A/C No. and the regards line
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
