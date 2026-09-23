"""
ENGINE — Excel Report Export
สร้างไฟล์ .xlsx ตามโครงสร้าง/ลำดับของ template L3_15MW_PTU_Calculation.xlsx ที่ยืนยันไว้:
  - Sheet "Summary"       : Load Transfer Under Failure + Main Equipment Sizing ต่อกลุ่ม
  - Sheet ต่อกลุ่ม (1 อันต่อ 1 PTU Group) : Load Calculation รายแถว (Normal + Fault ทุก scenario)
    ตามด้วย Transmission loss / Connected IT Load / UPS / HVAC / Transformer / Generator

ธีมสี/ฟอนต์/เส้นขอบ/ความกว้าง-สูง ทั้งหมด "ถอดมาจาก 6N5.xlsx" (ไฟล์ต้นแบบ format ที่ผู้ใช้ยืนยัน
2026-09) ผ่าน engine/excel_theme.py — แต่ละหัวข้อมีสีเป็นเอกลักษณ์ต่างกันตาม 6N5 จริง (Critical IT
Load/Transmission Loss = ฟ้า accent, Transformer = เขียว, Generator = เหลืองทอง, Summary = เหลืองอ่อน
ฯลฯ) ส่วน "ลำดับแถว / ข้อความ label / วิธีคำนวณ (สูตร)" ทั้งหมดยังเป็นของเราเองล้วนๆ ไม่ได้ยืมจาก 6N5
แม้บางจุดจะดูคล้ายกันก็ตาม (ยืนยันโดยผู้ใช้ 2026-09: "ลำดับ text วิธีการคำนวณยึดตามของเราเท่านั้น")

โครงสร้างข้อมูล (n_ups_per_group / n_group) เป็น dynamic เสมอ — ไม่ใช่ template คงที่ ทุกตำแหน่ง
คอลัมน์/แถวคำนวณจากพารามิเตอร์จริงที่ส่งเข้ามา ไม่มี hard-code ตัวอักษรคอลัมน์ใดๆ
ไม่มี st. ใดๆ ในไฟล์นี้ — รับ groups/cfg/group_calcs ที่คำนวณไว้แล้วจาก ui/tab_sizing.py มาตรงๆ
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from constants import ups_display_label, get_group_ups_units
from engine.pairing import compute_normal_loads, compute_fault_loads
from engine.excel_theme import (
    FILL, FONT, CENTER, CENTER_NOWRAP, LEFT, RIGHT,
    BORDER_OUTER, BORDER_DATA_ROW, BORDER_SUBTOTAL_ROW, BORDER_INNER_THIN, BORDER_INNER_HAIR,
    COL_WIDTH_ITEM, COL_WIDTH_DESC, COL_WIDTH_KW, COL_WIDTH_PF, COL_WIDTH_KVA,
    COL_WIDTH_DATA_FIRST, COL_WIDTH_DATA, COL_WIDTH_SPACER,
    ROW_HEIGHT, ROW_HEIGHT_TITLE, ROW_HEIGHT_HEADER,
    NUMFMT_KW, NUMFMT_KVA, NUMFMT_SUBTOTAL, NUMFMT_PCT,
    apply_theme, build_fail_arrow_text,
)

# ── Sheet "Summary" — ธีมสี "Data Center / Engineering Navy" เดิม (ยืนยันโดยผู้ใช้ 2026-09:
# กลับไปใช้แบบเก่า ไม่เอาธีม 6N5 กับหน้านี้ — 6N5 เองก็ไม่มี sheet แบบนี้อยู่แล้ว) ──────────
_SUMMARY_NAVY          = "1B365D"
_SUMMARY_GRID          = "D9D9D9"
SUMMARY_TITLE_FILL     = PatternFill("solid", fgColor=_SUMMARY_NAVY)
SUMMARY_HEADER_GREY    = PatternFill("solid", fgColor=_SUMMARY_GRID)
SUMMARY_OK_FILL        = PatternFill("solid", fgColor="E2F0D9")
SUMMARY_OVER_FILL      = PatternFill("solid", fgColor="FCE4E4")
SUMMARY_FAIL_CELL_FILL = PatternFill("solid", fgColor="FFC7CE")
SUMMARY_OK_FONT        = Font(color="375623", bold=True)
SUMMARY_OVER_FONT      = Font(color="C00000", bold=True)
SUMMARY_TITLE_FONT_LG  = Font(color="FFFFFF", bold=True, size=14)
SUMMARY_WHITE_BOLD     = Font(color="FFFFFF", bold=True)
SUMMARY_BOLD           = Font(bold=True)
_SUMMARY_THIN          = Side(style="thin", color=_SUMMARY_GRID)
_SUMMARY_MEDIUM_NAVY   = Side(style="medium", color=_SUMMARY_NAVY)
SUMMARY_BORDER         = Border(left=_SUMMARY_THIN, right=_SUMMARY_THIN, top=_SUMMARY_THIN, bottom=_SUMMARY_THIN)


def _border_range(ws, r1, c1, r2, c2, border):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).border = border


def _card_outline(ws, r1, c1, r2, c2):
    """ครอบ 'การ์ด' รอบตาราง Summary — grid บางสีเทาข้างใน + กรอบ navy หนาปานกลางรอบขอบนอก
    (ธีม navy เดิมของ Summary sheet — คนละธีมกับ sheet รายกลุ่มที่ยึด 6N5 โดยเจาะจง)"""
    _border_range(ws, r1, c1, r2, c2, SUMMARY_BORDER)
    for c in range(c1, c2 + 1):
        b = ws.cell(row=r1, column=c).border
        ws.cell(row=r1, column=c).border = Border(left=b.left, right=b.right, top=_SUMMARY_MEDIUM_NAVY, bottom=b.bottom)
        b = ws.cell(row=r2, column=c).border
        ws.cell(row=r2, column=c).border = Border(left=b.left, right=b.right, top=b.top, bottom=_SUMMARY_MEDIUM_NAVY)
    for r in range(r1, r2 + 1):
        b = ws.cell(row=r, column=c1).border
        ws.cell(row=r, column=c1).border = Border(left=_SUMMARY_MEDIUM_NAVY, right=b.right, top=b.top, bottom=b.bottom)
        b = ws.cell(row=r, column=c2).border
        ws.cell(row=r, column=c2).border = Border(left=b.left, right=_SUMMARY_MEDIUM_NAVY, top=b.top, bottom=b.bottom)


def _skip_cell(ws, row, col):
    """คอลัมน์ self-fail ที่ UPS ตัวเองพังไปแล้ว — เกรย์ไว้เฉยๆ ไม่คำนวณต่อ (ตามต้นแบบ 6N5:
    คอลัมน์ของตัวที่พังเองจะโดนเกรย์ตลอดทั้งสาย ตั้งแต่ subtotal ลงไปจนถึง Generator)"""
    c = ws.cell(row=row, column=col)
    c.value = None
    c.fill = FILL["data_selffail"]
    return c


def _write_group_sheet(wb, sheet_title, grp, cfg, equip, gi, n_ups_per_group=4):
    """
    Sheet รายกลุ่ม — Load Calculation รายแถว (Normal + Fault ทุก scenario)
    ตามโครงสร้าง 'L3 (PTU-...)' ของ template: ต่อ 1 แถว(HAC Row) มีคอลัมน์
    kW/PF/kW แล้วตามด้วย Normal(A,B,C,...) + spacer + [Fail A: ที่เหลือ] + spacer + ... ไล่ตาม
    n_ups_per_group (4 ตัวอักษร A-D เป็นค่า default — ตัวอักษรเป็น key คำนวณภายในเสมอ
    ป้ายแสดงผลไล่ต่อเนื่องตามกลุ่มจริงผ่าน ups_display_label)
    """
    ws = wb.create_sheet(title=sheet_title[:31])
    ws.sheet_view.showGridLines = True
    ups_units = get_group_ups_units(n_ups_per_group)
    scenarios = ["Normal"] + ups_units
    labels = {u: ups_display_label(gi, u, n_ups_per_group) for u in ups_units}

    # ── กำหนดตำแหน่งคอลัมน์ (F=6 เป็นต้นไป, เว้น 1 คอลัมน์คั่นทุก scenario) ──
    col = 6
    scenario_cols = {}
    spacer_cols = []
    for sc in scenarios:
        scenario_cols[sc] = list(range(col, col + n_ups_per_group))
        col += n_ups_per_group
        spacer_cols.append(col)   # คอลัมน์คั่นหลังบล็อกนี้ (โทนม่วงอ่อนตาม 6N5)
        col += 1
    last_col = col - 2  # ตัดคอลัมน์คั่นตัวสุดท้าย (เกินขอบตารางจริง) ออก
    spacer_cols = [c for c in spacer_cols if c <= last_col]

    # ── คอลัมน์ "self-fail" ของแต่ละ scenario fail (เช่น คอลัมน์ A ในบล็อก A Failure) ──
    # แถวสรุป/loss chain ทุกแถวใต้ IT Load จะไม่คำนวณอะไรในคอลัมน์นี้เลย (เกรย์ไว้เฉยๆ)
    # เพราะ UPS ตัวที่พังไปแล้ว ไม่มี "โหลดที่เหลือ" ให้เอามาคิด HVAC/Charging/Loss ต่อ
    self_fail_col = {}
    for sc in scenarios:
        if sc == "Normal":
            continue
        for u, col_i in zip(ups_units, scenario_cols[sc]):
            if u == sc:
                self_fail_col[sc] = col_i

    def _fill_spacers(row_i):
        for c in spacer_cols:
            ws.cell(row=row_i, column=c).fill = FILL["spacer"]

    # ── Title (เหลืองสด ตัวใหญ่ — เอกลักษณ์ของ 6N5) ──
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    t = ws.cell(row=1, column=1, value=f"Load Calculation for {sheet_title}")
    t.font = FONT["title"]
    t.alignment = CENTER
    t.fill = FILL["title"]
    ws.row_dimensions[1].height = ROW_HEIGHT_TITLE
    _border_range(ws, 1, 1, 1, last_col, BORDER_OUTER)

    # ── Header แถว 3: ชื่อ scenario ──
    ws.cell(row=3, column=1, value="Item").font = FONT["header"]
    ws.cell(row=3, column=1).fill = FILL["col_header"]
    d3 = ws.cell(row=3, column=2, value="Description")
    d3.font = FONT["header"]
    d3.fill = FILL["col_header"]
    ws.merge_cells(start_row=3, start_column=3, end_row=3, end_column=5)
    hc = ws.cell(row=3, column=3, value="Total Load")
    hc.font = FONT["header"]
    hc.alignment = CENTER
    hc.fill = FILL["col_header"]

    for sc in scenarios:
        cols = scenario_cols[sc]
        ws.merge_cells(start_row=3, start_column=cols[0], end_row=3, end_column=cols[-1])
        cell = ws.cell(row=3, column=cols[0],
                        value="Normal Operation" if sc == "Normal" else f"{labels[sc]} Failure")
        cell.font = FONT["header"]
        cell.alignment = CENTER
        cell.fill = FILL["normal_band"] if sc == "Normal" else FILL["fail_band"]
    _fill_spacers(3)

    # ── Header แถว 4: kW/PF/kW + A/B/C/D ──
    for j, label in enumerate(["kW", "PF", "kW"]):
        c = ws.cell(row=4, column=3 + j, value=label)
        c.font = FONT["header"]
        c.fill = FILL["col_header"]
        c.alignment = CENTER
    for sc in scenarios:
        for u, col_i in zip(ups_units, scenario_cols[sc]):
            is_fail_col = (sc != "Normal" and u == sc)
            cell = ws.cell(row=4, column=col_i, value=(f"{labels[u]} Fail" if is_fail_col else f"Load {labels[u]}"))
            cell.alignment = CENTER
            cell.font = FONT["header"]   # ตัวหนังสือดำเสมอ ตาม 6N5 จริง (แม้พื้นจะแดง/เขียวสด)
            if is_fail_col:
                cell.fill = FILL["selffail_sub"]
            elif sc == "Normal":
                cell.fill = FILL["normal_sub"]
            else:
                cell.fill = FILL["fail_sub"]
    _fill_spacers(4)

    _border_range(ws, 3, 1, 4, last_col, BORDER_INNER_THIN)
    ws.row_dimensions[3].height = ROW_HEIGHT_HEADER
    ws.row_dimensions[4].height = ROW_HEIGHT_HEADER

    # ── Data rows: 1 แถวต่อ HAC row ──
    row = 6
    r1 = ws.cell(row=row, column=1, value=1)
    r1.font = FONT["body_bold"]
    r2 = ws.cell(row=row, column=2, value="Critical IT Load")
    r2.font = FONT["body_bold"]
    for c in range(1, last_col + 1):
        ws.cell(row=row, column=c).fill = FILL["section_header"]
    row += 1
    ws.cell(row=row, column=2, value="IT Load").font = FONT["body_bold"]
    for c in range(1, last_col + 1):
        ws.cell(row=row, column=c).fill = FILL["subtotal"]
    row += 1

    data_start = row
    for i, r in enumerate(grp):
        if i % 2 == 1:
            for band_col in (1, 2, 3, 4, 5):
                ws.cell(row=row, column=band_col).fill = FILL["band_alt"]
        ws.cell(row=row, column=2, value=f"  - DATA HALL ({r['hac']} {r['side']})").font = FONT["body"]
        ws.cell(row=row, column=3, value=r["kw"]).font = FONT["body"]
        ws.cell(row=row, column=4, value=1.0).font = FONT["body"]
        ws.cell(row=row, column=5, value=r["kw"]).font = FONT["body"]

        n = compute_normal_loads([r], ups_units)
        for u, col_i in zip(ups_units, scenario_cols["Normal"]):
            v = n.get(u, 0.0)
            cell = ws.cell(row=row, column=col_i, value=(v if v else None))
            cell.font = FONT["body"]
            cell.fill = FILL["data_normal"]

        for faulted in ups_units:
            f = compute_fault_loads([r], faulted, ups_units)
            for u, col_i in zip(ups_units, scenario_cols[faulted]):
                cell = ws.cell(row=row, column=col_i)
                if u == faulted:
                    cell.fill = FILL["data_selffail"]
                    # ยืนยันโดยผู้ใช้ 2026-09: ถ้าแถวนี้จริงๆ อยู่ใน pair ของ UPS ที่พัง ให้บอกเลย
                    # ว่าโหลดวิ่งไปหาตัวไหนต่อ แบบ 6N5 ("A → B") — ตัวที่พังสีแดง ตัวที่รับสีเขียว
                    # ถ้าแถวนี้ไม่เกี่ยวกับ UPS ตัวที่พังเลย (ไม่ได้อยู่ใน pair) ก็ยังคงโชว์ "FAIL"
                    # เฉยๆ เหมือนเดิม เพราะไม่มีปลายทางที่จะบอกได้จริง (ไม่ใช่กรณีที่ user ขอ)
                    if faulted in r["pair"]:
                        survivors = [x for x in r["pair"] if x != faulted]
                        cell.value = build_fail_arrow_text(labels[faulted], [labels[s] for s in survivors])
                        cell.alignment = CENTER_NOWRAP
                    else:
                        cell.value = "FAIL"
                        cell.font = FONT["fail"]
                        cell.alignment = CENTER
                else:
                    v = f.get(u, 0.0)
                    cell.value = v if v else None
                    cell.font = FONT["body"]
                    cell.fill = FILL["data_fail"]
        _fill_spacers(row)
        row += 1
    data_end = row - 1

    for col_i in range(3, last_col + 1):
        for r in range(data_start, data_end + 1):
            cell = ws.cell(row=r, column=col_i)
            if isinstance(cell.value, (int, float)) or cell.value is None:
                cell.number_format = NUMFMT_KW
                cell.alignment = RIGHT if col_i >= 3 else LEFT

    # ── Total Power Consumption for Data Hall ──
    total_row = row
    ws.cell(row=total_row, column=2, value="Total Power Consumption for Data Hall").font = FONT["body_bold"]
    ws.cell(row=total_row, column=3, value=f"=SUM(C{data_start}:C{data_end})")
    ws.cell(row=total_row, column=5, value=f"=SUM(E{data_start}:E{data_end})")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, total_row, col_i)
                continue
            L = get_column_letter(col_i)
            ws.cell(row=total_row, column=col_i, value=f"=SUM({L}{data_start}:{L}{data_end})")
    _fill_spacers(total_row)
    for c in range(3, last_col + 1):
        cell = ws.cell(row=total_row, column=c)
        if cell.fill == FILL["data_selffail"]:
            continue
        cell.font = FONT["body_bold"]
        cell.fill = FILL["subtotal"]
        cell.number_format = NUMFMT_SUBTOTAL
        cell.alignment = RIGHT
    ws.cell(row=total_row, column=1).fill = FILL["subtotal"]
    ws.cell(row=total_row, column=2).fill = FILL["subtotal"]
    row += 2

    # ── Transmission loss (รอบ 1) — คิดแบบ loss ต้นทาง (ยืนยันโดยผู้ใช้ 2026-09): tx_loss% คือสัดส่วน
    # ของกำลังไฟที่ส่งจริง (ต้นทาง) ไม่ใช่ % ของโหลดปลายทาง (Total Power Consumption) ที่รู้ค่าอยู่แล้ว
    # จึงหารกลับ C{total_row}/(1-tx) เพื่อหาต้นทางก่อน แล้วลบ C{total_row}(ปลายทาง)ออกจึงได้ตัว loss เอง
    # ตรงกับ compute_load_chain() ใน engine/sizing.py (connected_it = it_kw / (1 - tx))
    tx = cfg["tx_loss"]
    tx1_row = row
    ws.cell(row=row, column=2, value=f"Transmission loss {tx * 100:.1f}%").font = FONT["body_bold"]
    ws.cell(row=row, column=3, value=f"=C{total_row}/(1-{tx})-C{total_row}")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, tx1_row, col_i)
                continue
            L = get_column_letter(col_i)
            ws.cell(row=tx1_row, column=col_i, value=f"={L}{total_row}/(1-{tx})-{L}{total_row}")
    _fill_spacers(tx1_row)
    for c in range(3, last_col + 1):
        cell = ws.cell(row=tx1_row, column=c)
        if cell.fill != FILL["data_selffail"]:
            cell.fill = FILL["subtotal"]
            cell.font = FONT["body_bold"]
            cell.number_format = NUMFMT_KW
            cell.alignment = RIGHT
    ws.cell(row=tx1_row, column=1).fill = FILL["subtotal"]
    ws.cell(row=tx1_row, column=2).fill = FILL["subtotal"]
    row += 1

    # ── Connected IT Load ──
    connected_row = row
    ws.cell(row=row, column=2, value="Connected IT Load").font = FONT["body_bold"]
    ws.cell(row=row, column=3, value=f"=C{total_row}+C{tx1_row}")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, connected_row, col_i)
                continue
            L = get_column_letter(col_i)
            ws.cell(row=connected_row, column=col_i, value=f"={L}{total_row}+{L}{tx1_row}")
    _fill_spacers(connected_row)
    for c in range(3, last_col + 1):
        cell = ws.cell(row=connected_row, column=c)
        cell.font = FONT["body_bold"]
        if cell.fill != FILL["data_selffail"]:
            cell.fill = FILL["subtotal"]
            cell.number_format = NUMFMT_KW
            cell.alignment = RIGHT
    ws.cell(row=connected_row, column=1).fill = FILL["subtotal"]
    ws.cell(row=connected_row, column=2).fill = FILL["subtotal"]
    row += 1

    row += 1

    def _chain_row(label, col_c_value, per_col_formula=None, bold=False, fmt=NUMFMT_KW, fill_role=None):
        """
        เขียน 1 แถว ทั้งคอลัมน์ C (Total) และทุก scenario column (F..last_col)
        - col_c_value: ค่า/สูตรสำหรับคอลัมน์ C
        - per_col_formula(L): callback รับ column letter คืนสูตรสำหรับคอลัมน์นั้น
          (ถ้าไม่ใส่ = ค่าคงที่ -> reference กลับไปที่ $C$row เหมือนกันทุกคอลัมน์ ตาม pattern ของ template ต้นแบบ)
        - fill_role: key ใน FILL ที่จะทาทั้งแถว (A ถึง last_col) — ให้แต่ละหัวข้อมีเอกลักษณ์สีต่างกันตาม 6N5
        """
        nonlocal row
        r = row
        lc = ws.cell(row=r, column=2, value=label)
        vc = ws.cell(row=r, column=3, value=col_c_value)
        vc.number_format = fmt
        vc.alignment = RIGHT
        font = FONT["body_bold"] if bold else FONT["body"]
        lc.font = font
        vc.font = font
        for sc in scenarios:
            for col_i in scenario_cols[sc]:
                if col_i == self_fail_col.get(sc):
                    _skip_cell(ws, r, col_i)
                    continue
                L = get_column_letter(col_i)
                formula = per_col_formula(L) if per_col_formula else f"=$C${r}"
                cell = ws.cell(row=r, column=col_i, value=formula)
                cell.number_format = fmt
                cell.font = font
                cell.alignment = RIGHT
        _fill_spacers(r)
        if fill_role:
            for c in range(1, last_col + 1):
                cell = ws.cell(row=r, column=c)
                if cell.fill != FILL["data_selffail"] and c not in spacer_cols:
                    cell.fill = FILL[fill_role]
        row += 1
        return r

    # ── UPS ──
    ups_row = _chain_row("Capacity of UPS IT", equip["ups"]["size"], bold=True, fill_role="capacity")
    util1 = ws.cell(row=row, column=2, value="Utilization (%)")
    util1.font = FONT["body_bold"]
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, row, col_i)
                continue
            L = get_column_letter(col_i)
            c = ws.cell(row=row, column=col_i, value=f"={L}{connected_row}/$C${ups_row}")
            c.number_format = NUMFMT_PCT
            c.font = FONT["body_bold"]
            c.alignment = RIGHT
    _fill_spacers(row)
    for c in range(1, last_col + 1):
        cell = ws.cell(row=row, column=c)
        if cell.fill != FILL["data_selffail"] and c not in spacer_cols:
            cell.fill = FILL["subtotal"]
    row += 2

    ups_loss_row = _chain_row(
        f"UPS Losses (Eff={cfg['ups_eff'] * 100:.0f}%)",
        f"=C{connected_row}*(1/{cfg['ups_eff']}-1)",
        per_col_formula=lambda L: f"={L}{connected_row}*(1/{cfg['ups_eff']}-1)")
    charging_row = _chain_row("UPS Charging", cfg["ups_charging"])
    ups_summary_row = _chain_row(
        "Summary of UPS Losses and Charging",
        f"=C{ups_loss_row}+C{charging_row}",
        per_col_formula=lambda L: f"={L}{ups_loss_row}+{L}{charging_row}",
        bold=True, fill_role="summary_highlight")
    row += 1

    # ── HVAC ──
    hvac_row = _chain_row("Summary of HVAC Loads", cfg["hvac_total"], bold=True, fill_role="summary_highlight")

    # ── Transmission loss รอบ 2 (PTU → Transformer/Generator) — เดิมขาดไปทั้งหมด ──
    tx2_row = _chain_row(
        f"Transmission loss {tx * 100:.1f}% (PTU→Trafo/Gen)",
        f"=(C{ups_summary_row}+C{hvac_row})*{tx}",
        per_col_formula=lambda L: f"=({L}{ups_summary_row}+{L}{hvac_row})*{tx}",
        bold=True, fill_role="section_header")
    row += 1

    # ── Total Connected Load / Transformer / Generator ──
    total_conn_row = _chain_row(
        "Total Connected Load",
        f"=C{connected_row}+C{ups_summary_row}+C{hvac_row}+C{tx2_row}",
        per_col_formula=lambda L: f"={L}{connected_row}+{L}{ups_summary_row}+{L}{hvac_row}+{L}{tx2_row}",
        bold=True, fill_role="total_connected")

    trafo_row = _chain_row("Capacity of Transformer", equip["trafo"]["size"], bold=True, fill_role="transformer")
    util2 = ws.cell(row=row, column=2, value="Utilization (%)")
    util2.font = FONT["body_bold"]
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, row, col_i)
                continue
            L = get_column_letter(col_i)
            c = ws.cell(row=row, column=col_i, value=f"={L}{total_conn_row}/$C${trafo_row}")
            c.number_format = NUMFMT_PCT
            c.font = FONT["body_bold"]
            c.alignment = RIGHT
    c = ws.cell(row=row, column=3, value=f"=C{total_conn_row}/C{trafo_row}")
    c.number_format = NUMFMT_PCT
    c.font = FONT["body_bold"]
    c.alignment = RIGHT
    _fill_spacers(row)
    for c in range(1, last_col + 1):
        cell = ws.cell(row=row, column=c)
        if cell.fill != FILL["data_selffail"] and c not in spacer_cols:
            cell.fill = FILL["transformer_util"]
    row += 2

    gen_row = _chain_row("Capacity of Generator", equip["gen"]["size"], bold=True, fill_role="generator")
    util3 = ws.cell(row=row, column=2, value="Utilization (%)")
    util3.font = FONT["body_bold"]
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, row, col_i)
                continue
            L = get_column_letter(col_i)
            c = ws.cell(row=row, column=col_i, value=f"={L}{total_conn_row}/$C${gen_row}")
            c.number_format = NUMFMT_PCT
            c.font = FONT["body_bold"]
            c.alignment = RIGHT
    c = ws.cell(row=row, column=3, value=f"=C{total_conn_row}/C{gen_row}")
    c.number_format = NUMFMT_PCT
    c.font = FONT["body_bold"]
    c.alignment = RIGHT
    _fill_spacers(row)
    for c in range(1, last_col + 1):
        cell = ws.cell(row=row, column=c)
        if cell.fill != FILL["data_selffail"] and c not in spacer_cols:
            cell.fill = FILL["generator_util"]
    row += 1

    # ── กรอบตารางเต็มความกว้าง ตั้งแต่ Data Hall ยันบรรทัดสุดท้าย ──
    _border_range(ws, data_start - 2, 1, row - 1, last_col, BORDER_DATA_ROW)

    for r in range(1, row):
        ws.row_dimensions[r].height = ROW_HEIGHT
    ws.row_dimensions[1].height = ROW_HEIGHT_TITLE
    ws.row_dimensions[3].height = ROW_HEIGHT_HEADER
    ws.row_dimensions[4].height = ROW_HEIGHT_HEADER

    ws.column_dimensions["A"].width = COL_WIDTH_ITEM
    ws.column_dimensions["B"].width = COL_WIDTH_DESC
    ws.column_dimensions["C"].width = COL_WIDTH_KW
    ws.column_dimensions["D"].width = COL_WIDTH_PF
    ws.column_dimensions["E"].width = COL_WIDTH_KVA
    for sc in scenarios:
        cols = scenario_cols[sc]
        ws.column_dimensions[get_column_letter(cols[0])].width = COL_WIDTH_DATA_FIRST
        for col_i in cols[1:]:
            ws.column_dimensions[get_column_letter(col_i)].width = COL_WIDTH_DATA
    for c in spacer_cols:
        ws.column_dimensions[get_column_letter(c)].width = COL_WIDTH_SPACER

    ws.freeze_panes = "C5"
    return ws


def _write_summary_sheet(wb, groups_data, n_ups_per_group=4):
    """
    Sheet 'Summary' — Load Transfer Under Failure (ต่อกลุ่ม) + Main Equipment Sizing
    groups_data: list ของ {"name": str, "grp": list[dict], "equip": dict, "gi": int}
    ธีม "Data Center / Engineering Navy" เดิม (ยืนยันโดยผู้ใช้ 2026-09: กลับไปใช้แบบเก่า
    ไม่เอาธีม 6N5 มาปนกับหน้านี้ — คนละ style กับ sheet รายกลุ่มโดยเจตนา)
    """
    ups_units = get_group_ups_units(n_ups_per_group)
    ws = wb.create_sheet(title="Summary", index=0)
    ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:H1")
    t = ws.cell(row=1, column=1, value="LEVEL 3 IT LOAD ANALYSIS — SUMMARY")
    t.font = SUMMARY_TITLE_FONT_LG
    t.fill = SUMMARY_TITLE_FILL
    t.alignment = CENTER
    ws.row_dimensions[1].height = 26

    row = 3
    for gd in groups_data:
        name, grp, equip, gi = gd["name"], gd["grp"], gd["equip"], gd["gi"]
        labels = {u: ups_display_label(gi, u, n_ups_per_group) for u in ups_units}

        card1_top = row
        ws.cell(row=row, column=1, value=f"{name} — Load Transfer Under Failure (kW)").font = Font(bold=True, color=_SUMMARY_NAVY, size=11)
        row += 1
        ws.cell(row=row, column=1, value="System").font = SUMMARY_BOLD
        ws.cell(row=row, column=1).fill = SUMMARY_HEADER_GREY
        for i, u in enumerate(ups_units):
            c = ws.cell(row=row, column=2 + i, value=labels[u])
            c.font = SUMMARY_WHITE_BOLD
            c.fill = SUMMARY_TITLE_FILL
            c.alignment = CENTER
        row += 1

        for faulted in ups_units:
            f = compute_fault_loads(grp, faulted, ups_units)
            ws.cell(row=row, column=1, value=f"{labels[faulted]} Failed").font = SUMMARY_BOLD
            for i, u in enumerate(ups_units):
                cell = ws.cell(row=row, column=2 + i)
                if u == faulted:
                    cell.value = None
                    cell.fill = SUMMARY_FAIL_CELL_FILL
                else:
                    v = f.get(u, 0.0)
                    cell.value = v if v else None
                    cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
            row += 1
        card1_bottom = row - 1
        _card_outline(ws, card1_top + 1, 1, card1_bottom, 1 + n_ups_per_group)
        row += 2

        card2_top = row
        ws.cell(row=row, column=1, value=f"{name} — Main Equipment Sizing").font = Font(bold=True, color=_SUMMARY_NAVY, size=11)
        row += 1
        headers = ["Item", "Size", "Unit", "Max Load", "Utilization", "Status"]
        for i, h in enumerate(headers):
            c = ws.cell(row=row, column=1 + i, value=h)
            c.font = SUMMARY_WHITE_BOLD
            c.fill = SUMMARY_TITLE_FILL
            c.alignment = CENTER
        row += 1

        for label, key, unit in [("UPS IT", "ups", "kW"), ("Transformer", "trafo", "kVA"),
                                  ("Generator", "gen", "kW"), ("Busway", "busway", "A")]:
            eq = equip[key]
            ws.cell(row=row, column=1, value=label)
            c2 = ws.cell(row=row, column=2, value=eq["size"])
            c2.number_format = "#,##0.00"
            c2.alignment = Alignment(horizontal="right", vertical="center")
            ws.cell(row=row, column=3, value=unit).alignment = CENTER
            c4 = ws.cell(row=row, column=4, value=eq["load"])
            c4.number_format = "#,##0.00"
            c4.alignment = Alignment(horizontal="right", vertical="center")
            status_cell = ws.cell(row=row, column=6)
            status_cell.alignment = CENTER
            if eq["size"] is None:
                ws.cell(row=row, column=5, value=None)
                status_cell.value = "N/A"
                status_cell.fill = SUMMARY_OVER_FILL
                status_cell.font = SUMMARY_OVER_FONT
            else:
                c5 = ws.cell(row=row, column=5, value=eq["util"])
                c5.number_format = "0.0%"
                c5.alignment = Alignment(horizontal="right", vertical="center")
                is_ok = eq["util"] is not None and eq["util"] <= 1.0
                status_cell.value = "OK" if is_ok else "OVER"
                status_cell.fill = SUMMARY_OK_FILL if is_ok else SUMMARY_OVER_FILL
                status_cell.font = SUMMARY_OK_FONT if is_ok else SUMMARY_OVER_FONT
            row += 1
        card2_bottom = row - 1
        _card_outline(ws, card2_top + 1, 1, card2_bottom, 6)
        row += 3   # เว้นระยะระหว่างกลุ่มให้ชัดเจน ไม่ติดกัน

    ws.column_dimensions["A"].width = 30
    for col_letter in ["B", "C", "D", "E", "F", "G", "H"]:
        ws.column_dimensions[col_letter].width = 14
    return ws


def build_excel_report(groups: list, cfg: dict, group_calcs: list, n_ups_per_group: int = 4) -> bytes:
    """
    groups          : list ของ list[dict] — ผลจาก milp_result["groups"] (1 list ต่อ 1 PTU group)
    cfg             : st.session_state.sizing_cfg (assumption ล่าสุด)
    group_calcs     : st.session_state.sizing_group_calcs -> [{"gi", "chain", "equip"}, ...]
                      (equip เป็นขนาดของกลุ่มนั้นๆ อิสระจากกลุ่มอื่น — group ใครกลุ่มมัน,
                      ไม่ unify ข้ามกลุ่มแล้ว — จาก PASS 1 ใน tab_sizing.py)
    n_ups_per_group : จำนวน PTU/UPS ต่อกลุ่ม (4/5/6) — จาก milp_result["n_ups_per_group"]

    คืนค่าเป็น bytes ของไฟล์ .xlsx พร้อมส่งให้ st.download_button ใช้ตรงๆ
    """
    wb = Workbook()
    wb.remove(wb.active)  # ลบ sheet ว่าง default ออกก่อน
    apply_theme(wb)       # ฝัง theme1.xml ของ 6N5.xlsx ก่อนเสมอ ไม่งั้นสี theme+tint ด้านบนจะผิดสี

    groups_data = []
    for calc in group_calcs:
        gi = calc["gi"]
        grp = groups[gi - 1]
        equip = calc["equip"]
        name = f"Group {gi}"
        _write_group_sheet(wb, name, grp, cfg, equip, gi, n_ups_per_group)
        groups_data.append({"name": name, "grp": grp, "equip": equip, "gi": gi})

    _write_summary_sheet(wb, groups_data, n_ups_per_group)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
