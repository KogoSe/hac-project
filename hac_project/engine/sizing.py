"""
ENGINE — Equipment Sizing (UPS / Transformer / Generator / Busway)
แยกออกจาก UI ชัดเจน ไม่มี st. ใดๆ ในไฟล์นี้
ใช้ร่วมกันได้ทั้ง tab 3 (Equipment Sizing) และ tab 4 (SLD) — import ตรงๆ ไม่ต้อง copy logic ซ้ำ
"""


def select_standard_size(required: float, size_list: list) -> float | None:
    """เลือก size เล็กสุดใน standard list ที่ >= required"""
    candidates = [s for s in sorted(size_list) if s >= required]
    return candidates[0] if candidates else None


def compute_load_chain(
    max_fault_it_kw: float,
    normal_it_kw: float,
    cfg: dict,
) -> dict:
    """
    คำนวณ Load Chain ทีละขั้น ทั้ง Normal และ Fault
    cfg: dict ของ assumption (eff, charging, tx_loss, hvac, pf, voltage, margin)
    Returns: dict ของทุก step ทั้ง normal และ fault
    """
    tx = cfg["tx_loss"]
    eff = cfg["ups_eff"]
    charging = cfg["ups_charging"]
    hvac = cfg["hvac_total"]
    pf = cfg["pf"]
    voltage = cfg["voltage"]
    margin = cfg["design_margin"]

    def chain(it_kw):
        # Step 2: Transmission loss ครั้งที่ 1 (IT → UPS)
        connected_it = it_kw * (1 + tx)
        # Step 3: UPS Loss + Charging
        ups_loss = connected_it * (1 / eff - 1)
        ups_total_out = connected_it + ups_loss + charging
        # Step 4: HVAC
        ptu_kw = ups_total_out + hvac
        ptu_kva = ptu_kw / pf
        # Step 5: Transmission loss ครั้งที่ 2 (PTU → Generator/Transformer)
        total_connected = ptu_kw * (1 + tx)
        total_connected_kva = total_connected / pf
        # Step 6: Busway current
        actual_amp = (ptu_kva * 1000) / (1.732 * voltage)
        design_amp = actual_amp * margin
        return {
            "it_kw":          it_kw,
            "connected_it":   connected_it,
            "ups_loss":       ups_loss,
            "ups_charging":   charging,
            "ups_total_out":  ups_total_out,
            "hvac":           hvac,
            "ptu_kw":         ptu_kw,
            "ptu_kva":        ptu_kva,
            "total_connected": total_connected,
            "total_connected_kva": total_connected_kva,
            "actual_amp":     actual_amp,
            "design_amp":     design_amp,
        }

    return {
        "normal": chain(normal_it_kw),
        "fault":  chain(max_fault_it_kw),
    }


def select_equipment(chain: dict, cfg: dict) -> dict:
    """
    เลือกขนาดอุปกรณ์จาก standard list โดยใช้ Fault load เป็น basis
    เลือกหลัง step ที่เกี่ยวข้องในการคำนวณ
    """
    f = chain["fault"]
    threshold = cfg["util_threshold"]

    # UPS: เลือกหลัง Step 2 — Connected IT Load
    ups_required = f["connected_it"] / threshold
    ups_size = select_standard_size(ups_required, cfg["ups_sizes"])
    ups_util = f["connected_it"] / ups_size if ups_size else None

    # Transformer: เลือกหลัง Step 5 — Total Connected Load (kVA) (บวก Transmission Loss ครั้งที่ 2 แล้ว)
    trafo_required = f["total_connected_kva"] / threshold
    trafo_size = select_standard_size(trafo_required, cfg["trafo_sizes"])
    trafo_util = f["total_connected_kva"] / trafo_size if trafo_size else None

    # Generator: เลือกหลัง Step 5 — Total Connected Load (kW)
    gen_required = f["total_connected"] / threshold
    gen_size = select_standard_size(gen_required, cfg["gen_sizes"])
    gen_util = f["total_connected"] / gen_size if gen_size else None

    # Busway: เลือกหลัง Step 6 — Design Ampere
    busway_size = select_standard_size(f["design_amp"], cfg["busway_sizes"])
    busway_util = f["design_amp"] / busway_size if busway_size else None

    return {
        "ups":    {"size": ups_size,    "unit": "kW",  "load": f["connected_it"],   "util": ups_util},
        "trafo":  {"size": trafo_size,  "unit": "kVA", "load": f["total_connected_kva"], "util": trafo_util},
        "gen":    {"size": gen_size,    "unit": "kW",  "load": f["total_connected"], "util": gen_util},
        "busway": {"size": busway_size, "unit": "A",   "load": f["design_amp"],      "util": busway_util},
    }


def unify_common_sizes(group_equip_list: list[dict], keys: tuple = ("ups", "gen", "trafo", "busway")) -> dict:
    """
    หาขนาดใหญ่สุดร่วมกันของแต่ละ equipment key จากทุกกลุ่ม แล้ว override
    equip['size']/['util'] ของทุกกลุ่มให้ใช้ขนาดเดียวกัน (util คำนวณใหม่จาก load เดิมของกลุ่มนั้น)

    group_equip_list: list ของ equip dict (ผลจาก select_equipment) — จะถูกแก้ไข in-place
    keys: equipment keys ที่ต้องการ unify ขนาดร่วมกัน
    Returns: dict ของขนาดร่วมที่เลือกใช้ เช่น {"ups": 2000.0, "gen": 3500.0, ...}
    """
    common_sizes = {}
    for key in keys:
        sizes = [eq[key]["size"] for eq in group_equip_list if eq[key]["size"] is not None]
        common_sizes[key] = max(sizes) if sizes else None

    for equip in group_equip_list:
        for key in keys:
            common_size = common_sizes[key]
            if common_size is not None:
                load = equip[key]["load"]
                equip[key]["size"] = common_size
                equip[key]["util"] = load / common_size if common_size else None

    return common_sizes

#เชื่อมระบบ

def select_it_and_preups_busbar(chain: dict, cfg: dict) -> dict:
    """
    เลือกขนาด Busbar เพิ่มอีก 2 จุด (นอกจาก Busway หลักใน select_equipment):
    - it_busbar: กระแสจาก connected_it (Step 2, ก่อน UPS loss) — ใช้กับ FINALBUSBAR/OUPS_MAINITBUSBAR/OUPS_ITBUSBAR_IF02
    - before_ups_busbar: กระแสจาก ups_total_out (Step 3, รวม UPS loss+charging) — ใช้กับ PTU_BUSBARBEFOREUPS
    ใช้ pf/voltage/design_margin ชุดเดียวกับ Busway หลัก ไม่หาร util_threshold (ตาม pattern เดิมของ busway)
    """
    f = chain["fault"]
    pf = cfg["pf"]
    voltage = cfg["voltage"]
    margin = cfg["design_margin"]

    def amp_from_kw(kw):
        kva = kw / pf
        actual_amp = (kva * 1000) / (1.732 * voltage)
        return actual_amp * margin

    it_amp = amp_from_kw(f["connected_it"])
    pre_amp = amp_from_kw(f["ups_total_out"])

    it_size = select_standard_size(it_amp, cfg["busway_sizes"])
    it_util = it_amp / it_size if it_size else None

    pre_size = select_standard_size(pre_amp, cfg["busway_sizes"])
    pre_util = pre_amp / pre_size if pre_size else None

    return {
        "it_busbar":         {"size": it_size,  "unit": "A", "load": it_amp,  "util": it_util},
        "before_ups_busbar": {"size": pre_size, "unit": "A", "load": pre_amp, "util": pre_util},
    }
