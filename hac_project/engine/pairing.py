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
    แปลง HAC DataFrame → list of row units อ่านจากแถวจริง 1 ต่อ 1 (ไม่ duplicate/mirror)
    แต่ละ row มี: hac, side, kw, rack_list, source_type
    kw = sum ของ rack_list (โหลดรวมต่อแถว)

    Validation: HAC Name เดียวกันต้องอยู่เป็นแถวติดกัน (consecutive), มีได้ 1-2 แถว, Side ห้ามซ้ำ
    ผิดเงื่อนไข → raise ValueError พร้อมข้อความชัดเจน (ห้าม silent fail)
    """
    rows = []
    seen_hac_names = set()
    for hac, group in itertools.groupby(df.to_dict("records"), key=lambda r: r["HAC Name"]):
        group = list(group)
        if hac in seen_hac_names:
            raise ValueError(f"HAC '{hac}': ชื่อซ้ำแบบไม่ติดกัน — แถวของ HAC เดียวกันต้องอยู่ติดกัน (consecutive) เท่านั้น")
        seen_hac_names.add(hac)

        if len(group) > 2:
            raise ValueError(f"HAC '{hac}': มี {len(group)} แถว — HAC หนึ่งมีได้สูงสุด 2 แถว (บน/ล่าง)")

        sides = [r.get("Side", "บน") for r in group]
        for s in sides:
            if s not in ("บน", "ล่าง"):
                raise ValueError(f"HAC '{hac}': Side ต้องเป็น 'บน' หรือ 'ล่าง' เท่านั้น (พบ: '{s}')")
        if len(sides) == 2 and sides[0] == sides[1]:
            raise ValueError(f"HAC '{hac}': Side ซ้ำกัน ('{sides[0]}' ทั้ง 2 แถว) — ต้องมีบน 1 แถว และล่าง 1 แถว ไม่ซ้ำกัน")

        for r in group:
            rack_list = parse_rack_layout(r.get("Rack Layout (kW)", ""))
            kw        = float(sum(rack_list)) if rack_list else 0.0
            src       = r.get("Source Type", "2-source")
            rows.append({"hac": hac, "side": r.get("Side", "บน"), "kw": kw, "rack_list": rack_list, "source_type": src})
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


def compute_normal_loads(grp: list[dict], ups_units: list = None) -> dict:
    """
    Normal operation โหลดบน UPS แต่ละตัว — ใช้ row['pair'] ตรงๆ ไม่ว่าจะยาว 2 ตัวอักษร (2-source,
    แบ่ง 50/50) หรือ 4 ตัวอักษร (4-source, แบ่ง 25% เท่ากัน — เสียบสายจริงแค่ 4 เส้นเสมอทางกายภาพ
    ไม่ว่ากลุ่มจะมี UPS ทั้งหมดกี่ตัว ซึ่งตัวไหนคือ 4 ตัวที่เสียบถูกกำหนดไว้แล้วใน row['pair'])
    ups_units: รายชื่อ UPS ทั้งหมดของกลุ่ม (default = 4 ตัวเดิม A,B,C,D เพื่อ backward compat)
    """
    if ups_units is None:
        ups_units = UPS_UNITS
    totals = {u: 0.0 for u in ups_units}
    for row in grp:
        members = row["pair"]
        share = row["kw"] / len(members)
        for u in members:
            totals[u] += share
    return totals


def compute_fault_loads(grp: list[dict], faulted: str, ups_units: list = None) -> dict:
    """
    Fault scenario: UPS 'faulted' พัง — ใช้ row['pair'] ตรงๆ เหมือน compute_normal_loads:
    ถ้า faulted เป็นสมาชิกของ row['pair'] สมาชิกที่เหลือ (survivors) แบ่งโหลดแถวนั้นเท่าๆกัน
    ถ้าไม่เกี่ยว แถวนั้นยังแบ่งโหลดปกติในหมู่สมาชิกของมันเหมือนเดิม ไม่ถูกกระทบ
    """
    if ups_units is None:
        ups_units = UPS_UNITS
    loads = {u: 0.0 for u in ups_units if u != faulted}
    for row in grp:
        members = row["pair"]
        if faulted in members:
            survivors = [u for u in members if u != faulted]
            share = row["kw"] / len(survivors)
            for u in survivors:
                loads[u] += share
        else:
            share = row["kw"] / len(members)
            for u in members:
                loads[u] += share
    return loads
