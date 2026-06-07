# Oasis Cotton Quotation Builder — Working Notes

Streamlit app that generates quotations as PDFs overlaid on a customer-uploaded
letterhead. Two production users: an internal sales person filling the form,
and a hosted Turso DB persisting drafts + archive across redeploys.

## Layout

| File | Role |
|------|------|
| `app.py` | Streamlit UI: 4-step form (Reference/Customer → Letterhead → Items → Footer/Bank), Drafts/Archive sidebar, Generate-PDF button |
| `quotation_pdf.py` | All PDF drawing (ReportLab) + final overlay onto the letterhead via pypdf |
| `storage.py` | Turso (libsql HTTPS) with local SQLite fallback. Tables: `drafts`, `archive` |
| `requirements.txt` | `streamlit pandas reportlab pypdf pymupdf openpyxl arabic-reshaper python-bidi libsql-client` |
| `DEPLOYMENT.md` | Streamlit Cloud + Turso setup |
| `Oasis Cotton Company - Letterhead.pdf` | The default letterhead used in dev |

## PDF rendering — read before touching `quotation_pdf.py`

ReportLab uses **Y=0 at the BOTTOM** of the page; A4 is 595×842pt. PyMuPDF
uses Y=0 at the **TOP**, so `rl_y = page_height - mupdf_y` when converting.

Vertical layout zones, all tunable in `generate_pdf()`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `TOP_LETTERHEAD_ZONE` | **auto-probed** | Reserved space at top for the letterhead's logo band. `_probe_top_letterhead_zone()` walks images/text/drawings in the top 200pt of the letterhead and reserves `lowest + 22pt`. Falls back to 170pt if PyMuPDF unavailable or probe finds nothing. Resolves to ~170pt for the repo letterhead. |
| `BOTTOM_LETTERHEAD_ZONE` | 130 | Reserved space at bottom for letterhead's QR + address band. Nothing the script draws may extend below this Y. |
| `TOTALS_FOOTER_RESERVE` | 234 | Vertical space needed for totals (3 rows × 18pt + 6pt gap = 60) + 22pt lead-in + footer text (138pt to last baseline + 3pt descender) = ~223pt actual ink + 11pt safety. Anything tighter (e.g. the old 240) loses pages to floating-point off-by-one against `BOTTOM_LETTERHEAD_ZONE`. |
| `CONTINUATION_PAGE_TOP_Y` | `= top_y` | Page 1 starts the QUOTATION box at `top_y`; continuation pages start their items column header at the same Y. Keep them equal or the letterhead clearance differs between pages. |

**Header box (8 rows + QUOTATION title, left side, 260pt wide):**
Every value runs through `wrap_to_width()`, so long fields (notably Address)
grow the row instead of overflowing. Labels are top-aligned with the first
value line so multi-line rows read naturally.

**Items table (6 cols, total 535pt):** `S.# | Item | Description | Qty. |
Unit Price | Total Price`. Both Item code and Description wrap; row height
grows to fit the taller column.

**Letterhead overlay:** quotation drawn on a separate canvas, then each page
merged onto a fresh re-parse of the letterhead via pypdf's
`bg_page.merge_page(layer_page)`. Re-parse per page is required — pypdf
mutates the page object.

## Storage

`storage.py` rewrites `libsql://...` → `https://...` before passing to
`libsql_client.create_client_sync()` because Streamlit Cloud blocks the WSS
transport that libsql's default scheme uses. The HTTPS endpoint is fine.

Local fallback: plain `sqlite3` against `quotation_store.db` in the project
folder. Activated automatically if `TURSO_DATABASE_URL` isn't set.

Sidebar caption reads "Storage backend: ☁️ Turso" or "💾 Local SQLite" so
you can confirm at a glance.

## Workflow constraints

**`main` is branch-protected.** Direct `git push origin main` returns
**403** from the local git proxy. All changes must land via PR + merge.

**Use GitHub MCP tools, not `git push`:**

1. `mcp__github__push_files` → creates branch + commit in one call
2. `mcp__github__create_pull_request`
3. `mcp__github__merge_pull_request` with `merge_method: "squash"`
4. After merge: `git fetch origin main && git reset --hard origin/main` to
   resync the local sandbox

**Credential degradation:** web-session GitHub write credentials can
silently degrade mid-session — every write returns
`403 Resource not accessible by integration` even though reads still work.
Symptoms: branch creation, file PUTs, and tree POSTs all fail with the same
message. **Land code changes early in a session.** If writes start 403ing,
no API workaround helps; the change must be applied from a different
environment (fresh web session, local Claude Code, or by the user manually).

**Streamlit Cloud auto-deploys** on every merge to `main` within 1-2
minutes. There is no manual deploy step.

## Recurring debugging patterns

Reproduce the rendered PDF in a Python REPL (deps available locally):

```python
import pandas as pd, fitz
from quotation_pdf import generate_pdf
items_df = pd.DataFrame([{'Item': '1', 'Product': 'X', 'Quantity': 1, 'Price': 1.0}])
header = {'q_ref': 'TEST', 'date': '07/06/2026', 'customer': 'X', ...}  # all PAYLOAD_FIELDS keys
pdf = generate_pdf(items_df, open('Oasis Cotton Company - Letterhead.pdf','rb').read(), header)
open('/tmp/r.pdf','wb').write(pdf)
fitz.open('/tmp/r.pdf')[0].get_pixmap(dpi=180).save('/tmp/r.png')
```

To trace page-break math, compute `top_y` from
`_probe_top_letterhead_zone()` then walk down: title (-18), 8 header rows
(-18 each, more if wrapped), -14 gap, -18 items header, -row_h_actual per
item. Page break before totals fires when
`items_y - TOTALS_FOOTER_RESERVE < BOTTOM_LETTERHEAD_ZONE`.

To inspect a letterhead's actual geometry:

```python
import fitz
page = fitz.open('letterhead.pdf')[0]
h = page.rect.height
for img in page.get_images(full=True):
    for r in page.get_image_rects(img[0]):
        print(f'image rl_top={h-r.y0:.0f} rl_bottom={h-r.y1:.0f}')
for blk in page.get_text('blocks'):
    print(f'text rl_top={h-blk[1]:.0f} rl_bottom={h-blk[3]:.0f}: {blk[4][:40]!r}')
```

## Known fragile spots

- **Letterhead probe** assumes header band ends within top 260pt of the
  page. A letterhead with a body image starting before that would inflate
  `TOP_LETTERHEAD_ZONE`. Tighten `start_max` / `end_max` if that breaks.
- **Item column wrap centering** — vertically centering the wrapped Item
  text broke rendering twice (PR f43129d, ee2871d both reverted). Leave it
  top-aligned.
- **Stop hook** complains about uncommitted changes after MCP-driven
  pushes succeed (local working tree falls behind `origin/main`). Resync
  with `git reset --hard origin/main`.
- **`data_editor` cell loss** if you write back to its session_state key
  after rendering. Let it own its key.
- **`st.session_state["author"]` (or any keyed widget) cannot be set after
  the widget renders** — throws `StreamlitAPIException`. Set before render
  or skip the overwrite.
