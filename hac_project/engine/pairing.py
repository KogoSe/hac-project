"""
ENGINE — HAC grouping / pairing / load calculation
แยกออกจาก UI ชัดเจน ไม่มี st. ใดๆ ในไฟล์นี้ เพื่อให้ tab ไหนก็เรียกใช้ได้ตรงๆ
"""
import itertools
import pandas as pd

from constants import UPS_UNITS, PAIR_ROTATION


def parse_rack_layout(layout_str: str) -> list[float]:
    """
    แปลง string เช่น "20, 150, 150, 150, 20" → [20.0, 150.0, 150.0, 150.0, 20.0]
    Returns [] ถ้า parse ไม่ได้
    """
    try:
        values = [float(x.strip()) for x in str(layout_str).split(",") if x.strip()]
        return values if values else []
    except Exception:
        return []


def build_row_units(df: pd.DataFrame) -> list[dict]:
    """
    แปลง HAC DataFrame → list of row units (top + bottom per HAC)
    แต่ละ row มี: hac, side, kw, rack_list, source_type
    kw = sum ของ rack_list (โหลดรวมต่อแถว)
    """
    rows = []
    for _, r in df.iterrows():
        rack_list = parse_rack_layout(r.get("Rack Layout (kW)", ""))
        kw        = float(sum(rack_list)) if rack_list else 0.0
        src       = r.get("Source Type", "2-source")
        rows.append({"hac": r["HAC Name"], "side": "บน",   "kw": kw, "rack_list": rack_list, "source_type": src})
        rows.append({"hac": r["HAC Name"], "side": "ล่าง", "kw": kw, "rack_list": rack_list, "source_type": src})
    return rows


def brute_force_grouping(row_units: list[dict], n_groups: int) -> tuple[list, float]:
    """
    แบ่งแถวเป็น n_groups กลุ่มเรียงต่อกัน ไม่ข้าม
    เกณฑ์: minimize (max_group_kw - min_group_kw)
    """
    n      = len(row_units)
    prefix = [0.0]
    for r in row_units:
        prefix.append(prefix[-1] + r["kw"])

    def group_sum(a, b):
        return prefix[b] - prefix[a]

    best_cuts   = None
    best_spread = float("inf")

    for cuts in itertools.combinations(range(1, n), n_groups - 1):
        boundaries = [0] + list(cuts) + [n]
        totals     = [group_sum(boundaries[i], boundaries[i + 1]) for i in range(n_groups)]
        spread     = max(totals) - min(totals)
        if spread < best_spread:
            best_spread = spread
            best_cuts   = boundaries

    groups = [row_units[best_cuts[i]:best_cuts[i + 1]] for i in range(n_groups)]
    return groups, best_spread


def assign_pairing(groups: list[list]) -> list[list]:
    """
    กำหนด Pairing แต่ละแถว:
    - 2-source → non-overlapping rotation (AB/CD/AC/BD/AD/BC)
    - 4-source → "ABCD" (รับทุก UPS ไม่ต้อง assign Pairing)
    rotation index นับเฉพาะ 2-source เท่านั้น เพื่อไม่ให้ sequence หลุด
    """
    result = []
    for grp in groups:
        grp_copy = []
        pair_idx = 0  # นับเฉพาะ 2-source rows
        for row in grp:
            r = dict(row)
            if r["source_type"] == "4-source":
                r["pair"] = "ABCD"
            else:
                r["pair"] = PAIR_ROTATION[pair_idx % len(PAIR_ROTATION)]
                pair_idx += 1
            grp_copy.append(r)
        result.append(grp_copy)
    return result


def compute_normal_loads(grp: list[dict]) -> dict:
    """
    Normal operation โหลดบน UPS แต่ละตัว:
    - 2-source: 50/50 ไปหา 2 UPS ที่ Pair กัน
    - 4-source: 25% ไปหาทุก UPS (A/B/C/D)
    """
    totals = {u: 0.0 for u in UPS_UNITS}
    for row in grp:
        if row["source_type"] == "4-source":
            share = row["kw"] / 4
            for u in UPS_UNITS:
                totals[u] += share
        else:
            half = row["kw"] / 2
            totals[row["pair"][0]] += half
            totals[row["pair"][1]] += half
    return totals


def compute_fault_loads(grp: list[dict], faulted: str) -> dict:
    """
    Fault scenario: UPS 'faulted' พัง
    2-source:
      - แถวที่ faulted อยู่ใน Pairing → Partner รับ 100%
      - แถวที่ไม่เกี่ยว → ยังแบ่ง 50/50 ตามปกติ
    4-source:
      - faulted หายไป → 3 ตัวที่เหลือรับ 33.33% แต่ละตัว (รวม = 100%)
    """
    loads = {u: 0.0 for u in UPS_UNITS if u != faulted}
    for row in grp:
        if row["source_type"] == "4-source":
            share = row["kw"] / 3  # 3 ตัวที่รอดแบ่งเท่ากัน
            for u in loads:
                loads[u] += share
        else:
            u1, u2 = row["pair"][0], row["pair"][1]
            if faulted in (u1, u2):
                partner = u2 if faulted == u1 else u1
                loads[partner] += row["kw"]
            else:
                half = row["kw"] / 2
                loads[u1] += half
                loads[u2] += half
    return loads
