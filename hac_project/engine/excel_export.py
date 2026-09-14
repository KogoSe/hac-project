"""
ENGINE — Excel Report Export
สร้างไฟล์ .xlsx ตามโครงสร้าง/ลำดับของ template L3_15MW_PTU_Calculation.xlsx ที่ยืนยันไว้:
  - Sheet "Summary"       : Load Transfer Under Failure + Main Equipment Sizing ต่อกลุ่ม
  - Sheet ต่อกลุ่ม (1 อันต่อ 1 PTU Group) : Load Calculation รายแถว (Normal + Fault ทุก scenario)
    ตามด้วย Transmission loss / Connected IT Load / UPS / HVAC / Transformer / Generator

สีปรับเองตามธีมแอป (เขียว=Normal, แดง=Fail) — โครงสร้าง/ลำดับคอลัมน์ตาม template
ไม่มี st. ใดๆ ในไฟล์นี้ — รับ groups/cfg/group_calcs ที่คำนวณไว้แล้วจาก ui/tab_sizing.py มาตรงๆ
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from constants import UPS_UNITS
from engine.pairing import compute_normal_loads, compute_fault_loads

# ── สี (โทนเดียวกับ Section 4.5 ใน tab_result.py) ──────────────
NORMAL_FILL    = PatternFill("solid", fgColor="C6E0B4")   # เขียวอ่อน
FAIL_FILL      = PatternFill("solid", fgColor="F8CBAD")   # แดง/ส้มอ่อน (หัวกลุ่ม fail)
FAIL_CELL_FILL = PatternFill("solid", fgColor="FFC7CE")   # แดงเข้มขึ้น (cell ที่ fail จริง)
TITLE_FILL     = PatternFill("solid", fgColor="1F4E79")
SUBTOTAL_FILL  = PatternFill("solid", fgColor="FFF2CC")
HEADER_GREY    = PatternFill("solid", fgColor="D9D9D9")
OK_FILL        = PatternFill("solid", fgColor="C6E0B4")
OVER_FILL      = PatternFill("solid", fgColor="FFC7CE")
GREY_SKIP_FILL = PatternFill("solid", fgColor="D9D9D9")   # คอลัมน์ self-fail ที่ไม่คำนวณต่อ (ตามต้นแบบ)

WHITE_BOLD = Font(color="FFFFFF", bold=True)
BOLD       = Font(bold=True)
RED_BOLD   = Font(color="C00000", bold=True)

THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center")


def _border_range(ws, r1, c1, r2, c2):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).border = BORDER


def _skip_cell(ws, row, col):
    """คอลัมน์ self-fail ที่ UPS ตัวเองพังไปแล้ว — เกรย์ไว้เฉยๆ ไม่คำนวณต่อ (ตามต้นแบบ)"""
    c = ws.cell(row=row, column=col)
    c.value = None
    c.fill = GREY_SKIP_FILL
    return c


def _write_group_sheet(wb, sheet_title, grp, cfg, equip):
    """
    Sheet รายกลุ่ม — Load Calculation รายแถว (Normal + Fault ทุก scenario)
    ตามโครงสร้าง 'L3 (PTU-...)' ของ template: ต่อ 1 แถว(HAC Row) มีคอลัมน์
    kW/PF/kW แล้วตามด้วย Normal(A,B,C,D) + spacer + [Fail A: B,C,D] + spacer +
    [Fail B: A,C,D] + spacer + [Fail C: A,B,D] + spacer + [Fail D: A,B,C]
    """
    ws = wb.create_sheet(title=sheet_title[:31])
    scenarios = ["Normal"] + UPS_UNITS

    # ── กำหนดตำแหน่งคอลัมน์ (F=6 เป็นต้นไป, เว้น 1 คอลัมน์คั่นทุก scenario) ──
    col = 6
    scenario_cols = {}
    for sc in scenarios:
        scenario_cols[sc] = list(range(col, col + 4))
        col += 5  # 4 คอลัมน์ + spacer
    last_col = col - 2

    # ── คอลัมน์ "self-fail" ของแต่ละ scenario fail (เช่น คอลัมน์ A ในบล็อก A Failure) ──
    # แถวสรุป/loss chain ทุกแถวใต้ IT Load จะไม่คำนวณอะไรในคอลัมน์นี้เลย (เกรย์ไว้เฉยๆ)
    # เพราะ UPS ตัวที่พังไปแล้ว ไม่มี "โหลดที่เหลือ" ให้เอามาคิด HVAC/Charging/Loss ต่อ
    self_fail_col = {}
    for sc in scenarios:
        if sc == "Normal":
            continue
        for u, col_i in zip(UPS_UNITS, scenario_cols[sc]):
            if u == sc:
                self_fail_col[sc] = col_i

    # ── Title ──
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    t = ws.cell(row=1, column=1, value=f"Load Calculation for {sheet_title}")
    t.font = WHITE_BOLD
    t.alignment = CENTER
    t.fill = TITLE_FILL
    ws.row_dimensions[1].height = 22

    # ── Header แถว 3: ชื่อ scenario ──
    ws.cell(row=3, column=1, value="Item").font = BOLD
    ws.cell(row=3, column=2, value="Description").font = BOLD
    ws.merge_cells(start_row=3, start_column=3, end_row=3, end_column=5)
    hc = ws.cell(row=3, column=3, value="Total Load")
    hc.font = BOLD
    hc.alignment = CENTER
    hc.fill = HEADER_GREY

    for sc in scenarios:
        cols = scenario_cols[sc]
        ws.merge_cells(start_row=3, start_column=cols[0], end_row=3, end_column=cols[-1])
        cell = ws.cell(row=3, column=cols[0],
                        value="Normal Operation" if sc == "Normal" else f"{sc} Failure")
        cell.font = WHITE_BOLD
        cell.alignment = CENTER
        cell.fill = NORMAL_FILL if sc == "Normal" else FAIL_FILL

    # ── Header แถว 4: kW/PF/kW + A/B/C/D ──
    for j, label in enumerate(["kW", "PF", "kW"]):
        c = ws.cell(row=4, column=3 + j, value=label)
        c.font = BOLD
        c.alignment = CENTER
    for sc in scenarios:
        for u, col_i in zip(UPS_UNITS, scenario_cols[sc]):
            is_fail_col = (sc != "Normal" and u == sc)
            cell = ws.cell(row=4, column=col_i, value=(f"{u} Fail" if is_fail_col else f"Load {u}"))
            cell.alignment = CENTER
            if is_fail_col:
                cell.font = Font(color="C00000", bold=True)
                cell.fill = FAIL_CELL_FILL
            else:
                cell.font = BOLD

    _border_range(ws, 3, 1, 4, last_col)

    # ── Data rows: 1 แถวต่อ HAC row ──
    row = 6
    ws.cell(row=row, column=1, value=1).font = BOLD
    ws.cell(row=row, column=2, value="Critical IT Load").font = BOLD
    row += 1
    ws.cell(row=row, column=2, value="IT Load").font = BOLD
    row += 1

    BAND_FILL = PatternFill("solid", fgColor="F2F2F2")

    data_start = row
    for i, r in enumerate(grp):
        if i % 2 == 1:
            for band_col in (1, 2, 3, 4, 5):
                ws.cell(row=row, column=band_col).fill = BAND_FILL
        ws.cell(row=row, column=2, value=f"  - DATA HALL ({r['hac']} {r['side']})")
        ws.cell(row=row, column=3, value=r["kw"])
        ws.cell(row=row, column=4, value=1.0)
        ws.cell(row=row, column=5, value=r["kw"])

        n = compute_normal_loads([r])
        for u, col_i in zip(UPS_UNITS, scenario_cols["Normal"]):
            v = n.get(u, 0.0)
            ws.cell(row=row, column=col_i, value=(v if v else None))

        for faulted in UPS_UNITS:
            f = compute_fault_loads([r], faulted)
            for u, col_i in zip(UPS_UNITS, scenario_cols[faulted]):
                if u == faulted:
                    cell = ws.cell(row=row, column=col_i, value="FAIL")
                    cell.font = RED_BOLD
                    cell.fill = FAIL_CELL_FILL
                    cell.alignment = CENTER
                else:
                    v = f.get(u, 0.0)
                    ws.cell(row=row, column=col_i, value=(v if v else None))
        row += 1
    data_end = row - 1

    for col_i in range(3, last_col + 1):
        for r in range(data_start, data_end + 1):
            ws.cell(row=r, column=col_i).number_format = "#,##0.0"

    # ── Total Power Consumption for Data Hall ──
    total_row = row
    ws.cell(row=total_row, column=2, value="Total Power Consumption for Data Hall").font = BOLD
    ws.cell(row=total_row, column=3, value=f"=SUM(C{data_start}:C{data_end})")
    ws.cell(row=total_row, column=5, value=f"=SUM(E{data_start}:E{data_end})")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, total_row, col_i)
                continue
            L = get_column_letter(col_i)
            ws.cell(row=total_row, column=col_i, value=f"=SUM({L}{data_start}:{L}{data_end})")
    for c in range(3, last_col + 1):
        cell = ws.cell(row=total_row, column=c)
        if cell.fill == GREY_SKIP_FILL:
            continue
        cell.font = BOLD
        cell.fill = SUBTOTAL_FILL
        cell.number_format = "#,##0.0"
    row += 2

    # ── Transmission loss (รอบ 1) ──
    tx = cfg["tx_loss"]
    tx1_row = row
    ws.cell(row=row, column=2, value=f"Transmission loss {tx * 100:.1f}%")
    ws.cell(row=row, column=3, value=f"=C{total_row}*{tx}")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, tx1_row, col_i)
                continue
            L = get_column_letter(col_i)
            ws.cell(row=tx1_row, column=col_i, value=f"={L}{total_row}*{tx}")
    for c in range(3, last_col + 1):
        cell = ws.cell(row=tx1_row, column=c)
        if cell.fill != GREY_SKIP_FILL:
            cell.number_format = "#,##0.0"
    row += 1

    # ── Connected IT Load ──
    connected_row = row
    ws.cell(row=row, column=2, value="Connected IT Load").font = BOLD
    ws.cell(row=row, column=3, value=f"=C{total_row}+C{tx1_row}")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, connected_row, col_i)
                continue
            L = get_column_letter(col_i)
            ws.cell(row=connected_row, column=col_i, value=f"={L}{total_row}+{L}{tx1_row}")
    for c in range(3, last_col + 1):
        cell = ws.cell(row=connected_row, column=c)
        cell.font = BOLD
        if cell.fill != GREY_SKIP_FILL:
            cell.number_format = "#,##0.0"
    row += 1

    row += 1

    def _chain_row(label, col_c_value, per_col_formula=None, bold=False, fmt="#,##0.0", banded=False):
        """
        เขียน 1 แถว ทั้งคอลัมน์ C (Total) และทุก scenario column (F..last_col)
        - col_c_value: ค่า/สูตรสำหรับคอลัมน์ C
        - per_col_formula(L): callback รับ column letter คืนสูตรสำหรับคอลัมน์นั้น
          (ถ้าไม่ใส่ = ค่าคงที่ -> reference กลับไปที่ $C$row เหมือนกันทุกคอลัมน์ ตาม pattern ของ template ต้นแบบ)
        """
        nonlocal row
        r = row
        lc = ws.cell(row=r, column=2, value=label)
        vc = ws.cell(row=r, column=3, value=col_c_value)
        vc.number_format = fmt
        if bold:
            lc.font = BOLD
            vc.font = BOLD
        for sc in scenarios:
            for col_i in scenario_cols[sc]:
                if col_i == self_fail_col.get(sc):
                    _skip_cell(ws, r, col_i)
                    continue
                L = get_column_letter(col_i)
                formula = per_col_formula(L) if per_col_formula else f"=$C${r}"
                cell = ws.cell(row=r, column=col_i, value=formula)
                cell.number_format = fmt
                if bold:
                    cell.font = BOLD
        if banded:
            for c in range(2, last_col + 1):
                cell = ws.cell(row=r, column=c)
                if cell.fill != GREY_SKIP_FILL:
                    cell.fill = SUBTOTAL_FILL
        row += 1
        return r

    # ── UPS ──
    ups_row = _chain_row("Capacity of UPS IT", equip["ups"]["size"], bold=True)
    ws.cell(row=row, column=2, value="Utilization (%)")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, row, col_i)
                continue
            L = get_column_letter(col_i)
            c = ws.cell(row=row, column=col_i, value=f"={L}{connected_row}/$C${ups_row}")
            c.number_format = "0.0%"
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
        bold=True, banded=True)
    row += 1

    # ── HVAC ──
    hvac_row = _chain_row("Summary of HVAC Loads", cfg["hvac_total"], bold=True, banded=True)

    # ── Transmission loss รอบ 2 (PTU → Transformer/Generator) — เดิมขาดไปทั้งหมด ──
    tx2_row = _chain_row(
        f"Transmission loss {tx * 100:.1f}% (PTU→Trafo/Gen)",
        f"=(C{ups_summary_row}+C{hvac_row})*{tx}",
        per_col_formula=lambda L: f"=({L}{ups_summary_row}+{L}{hvac_row})*{tx}")
    row += 1

    # ── Total Connected Load / Transformer / Generator ──
    total_conn_row = _chain_row(
        "Total Connected Load",
        f"=C{connected_row}+C{ups_summary_row}+C{hvac_row}+C{tx2_row}",
        per_col_formula=lambda L: f"={L}{connected_row}+{L}{ups_summary_row}+{L}{hvac_row}+{L}{tx2_row}",
        bold=True, banded=True)

    trafo_row = _chain_row("Capacity of Transformer", equip["trafo"]["size"], bold=True)
    ws.cell(row=row, column=2, value="Utilization (%)")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, row, col_i)
                continue
            L = get_column_letter(col_i)
            c = ws.cell(row=row, column=col_i, value=f"={L}{total_conn_row}/$C${trafo_row}")
            c.number_format = "0.0%"
    c = ws.cell(row=row, column=3, value=f"=C{total_conn_row}/C{trafo_row}")
    c.number_format = "0.0%"
    row += 2

    gen_row = _chain_row("Capacity of Generator", equip["gen"]["size"], bold=True)
    ws.cell(row=row, column=2, value="Utilization (%)")
    for sc in scenarios:
        for col_i in scenario_cols[sc]:
            if col_i == self_fail_col.get(sc):
                _skip_cell(ws, row, col_i)
                continue
            L = get_column_letter(col_i)
            c = ws.cell(row=row, column=col_i, value=f"={L}{total_conn_row}/$C${gen_row}")
            c.number_format = "0.0%"
    c = ws.cell(row=row, column=3, value=f"=C{total_conn_row}/C{gen_row}")
    c.number_format = "0.0%"
    row += 1

    # ── กรอบตารางเต็มความกว้าง ตั้งแต่ Data Hall ยันบรรทัดสุดท้าย ──
    _border_range(ws, data_start - 2, 1, row - 1, last_col)

    ws.column_dimensions["B"].width = 34
    for col_i in range(3, last_col + 1):
        ws.column_dimensions[get_column_letter(col_i)].width = 11
    ws.freeze_panes = "C5"
    return ws


def _write_summary_sheet(wb, groups_data):
    """
    Sheet 'Summary' — Load Transfer Under Failure (ต่อกลุ่ม) + Main Equipment Sizing
    groups_data: list ของ {"name": str, "grp": list[dict], "equip": dict}
    """
    ws = wb.create_sheet(title="Summary", index=0)
    ws.merge_cells("A1:H1")
    t = ws.cell(row=1, column=1, value="LEVEL 3 IT LOAD ANALYSIS — SUMMARY")
    t.font = WHITE_BOLD
    t.fill = TITLE_FILL
    t.alignment = CENTER
    ws.row_dimensions[1].height = 22

    row = 3
    for gd in groups_data:
        name, grp, equip = gd["name"], gd["grp"], gd["equip"]

        ws.cell(row=row, column=1, value=f"{name} — Load Transfer Under Failure (kW)").font = BOLD
        row += 1
        ws.cell(row=row, column=1, value="System").font = BOLD
        for i, u in enumerate(UPS_UNITS):
            c = ws.cell(row=row, column=2 + i, value=u)
            c.font = WHITE_BOLD
            c.fill = TITLE_FILL
            c.alignment = CENTER
        row += 1

        for faulted in UPS_UNITS:
            f = compute_fault_loads(grp, faulted)
            ws.cell(row=row, column=1, value=f"{faulted} Failed")
            for i, u in enumerate(UPS_UNITS):
                cell = ws.cell(row=row, column=2 + i)
                if u == faulted:
                    cell.value = None
                    cell.fill = FAIL_CELL_FILL
                else:
                    v = f.get(u, 0.0)
                    cell.value = v if v else None
                    cell.number_format = "#,##0.0"
            row += 1
        row += 1

        ws.cell(row=row, column=1, value=f"{name} — Main Equipment Sizing").font = BOLD
        row += 1
        headers = ["Item", "Size", "Unit", "Max Load", "Utilization", "Status"]
        for i, h in enumerate(headers):
            c = ws.cell(row=row, column=1 + i, value=h)
            c.font = BOLD
            c.fill = HEADER_GREY
        row += 1

        for label, key, unit in [("UPS IT", "ups", "kW"), ("Transformer", "trafo", "kVA"),
                                  ("Generator", "gen", "kW"), ("Busway", "busway", "A")]:
            eq = equip[key]
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=eq["size"])
            ws.cell(row=row, column=3, value=unit)
            c4 = ws.cell(row=row, column=4, value=eq["load"])
            c4.number_format = "#,##0.0"
            status_cell = ws.cell(row=row, column=6)
            if eq["size"] is None:
                ws.cell(row=row, column=5, value=None)
                status_cell.value = "N/A"
                status_cell.fill = OVER_FILL
            else:
                c5 = ws.cell(row=row, column=5, value=eq["util"])
                c5.number_format = "0.0%"
                is_ok = eq["util"] is not None and eq["util"] <= 1.0
                status_cell.value = "OK" if is_ok else "OVER"
                status_cell.fill = OK_FILL if is_ok else OVER_FILL
            row += 1
        row += 2

    ws.column_dimensions["A"].width = 26
    for col_letter in ["B", "C", "D", "E", "F", "G", "H"]:
        ws.column_dimensions[col_letter].width = 13
    return ws


def build_excel_report(groups: list, cfg: dict, group_calcs: list) -> bytes:
    """
    groups       : list ของ list[dict] — ผลจาก milp_result["groups"] (1 list ต่อ 1 PTU group)
    cfg          : st.session_state.sizing_cfg (assumption ล่าสุด)
    group_calcs  : st.session_state.sizing_group_calcs -> [{"gi", "chain", "equip"}, ...]
                   (equip ต้องเป็นค่าที่ unify_common_sizes() แล้ว — ของเดิมจาก PASS 1 ใน tab_sizing.py)

    คืนค่าเป็น bytes ของไฟล์ .xlsx พร้อมส่งให้ st.download_button ใช้ตรงๆ
    """
    wb = Workbook()
    wb.remove(wb.active)  # ลบ sheet ว่าง default ออกก่อน

    groups_data = []
    for calc in group_calcs:
        gi = calc["gi"]
        grp = groups[gi - 1]
        equip = calc["equip"]
        name = f"Group {gi}"
        _write_group_sheet(wb, name, grp, cfg, equip)
        groups_data.append({"name": name, "grp": grp, "equip": equip})

    _write_summary_sheet(wb, groups_data)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()