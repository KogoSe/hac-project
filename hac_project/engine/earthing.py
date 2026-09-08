"""
ENGINE — Earthing / Ground Cable Sizing (BS 7671, Table 43A: S = I*sqrt(t)/k)
แยกออกจาก UI ชัดเจน ไม่มี st. ใดๆ ในไฟล์นี้

หลักการ (แก้ไข 2026-09 — ยืนยันโดยผู้ใช้):
- ไม่ใช้ฐานคำนวณเดียว (max ของ Trafo/Gen) แบบเดิมอีกต่อไป
- แยกคำนวณ 2 ฐานอิสระกัน:
    - ฐาน Transformer (trafo_kva) → ใช้กับ RMU_S_GROUNDCABLE, TX_S_GROUNDCABLE
    - ฐาน Generator (gen_kw/gen_pf → kVA) → ใช้กับ GEN_S_GROUNDCABLE, PTU_GROUNDCABLE
- Fault Level (Ik) ของแต่ละฐาน มาจาก %Z ของอุปกรณ์ตัวนั้นเอง (ไม่ใช้ network impedance เต็มรูปแบบ)
"""
import re
import math

# BS 7671 Table 43A — Values of k for common materials
# key: (conductor_material, insulation_label) -> k value
TABLE_43A_K_VALUES = {
    "Copper — 70°C thermoplastic (PVC)":  115,
    "Copper — 90°C thermoplastic (PVC)":  100,
    "Copper — 60°C thermosetting (rubber)": 141,
    "Copper — 85°C thermosetting (rubber)": 134,
    "Copper — 90°C thermosetting":         143,
    "Copper — Impregnated paper":          108,
    "Aluminium — 70°C thermoplastic (PVC)": 76,
    "Aluminium — 90°C thermoplastic (PVC)": 66,
    "Aluminium — 60°C thermosetting (rubber)": 93,
    "Aluminium — 85°C thermosetting (rubber)": 89,
    "Aluminium — 90°C thermosetting":       94,
}


def compute_full_load_current(kva: float, voltage: float) -> float:
    """I_rated (A) จาก kVA — สูตร I = kVA*1000 / (sqrt(3) * V)"""
    return (kva * 1000) / (math.sqrt(3) * voltage)


def compute_fault_level_ka(kva: float, voltage: float, pct_z: float) -> float:
    """Fault Level Ik (kA) จาก %Z — Ik = I_rated / (%Z/100)"""
    i_rated = compute_full_load_current(kva, voltage)
    ik_a = i_rated / (pct_z / 100)
    return ik_a / 1000


def _compute_ground_cable_single(
    base_kva: float,
    base_label: str,
    voltage: float,
    pct_z: float,
    fault_margin_pct: float,
    fault_duration_sec: float,
    k_value: float,
    cable_sizes: list,
    n_sets: int,
) -> dict:
    """คำนวณขนาดสายดินตาม BS 7671 (S = I*sqrt(t)/k) จากฐานคำนวณเดียว (base_kva)
    ใช้เป็น helper ภายในเท่านั้น — เรียกผ่าน compute_ground_cable_dual()"""
    i_rated = compute_full_load_current(base_kva, voltage)
    ik_ka = i_rated / (pct_z / 100) / 1000
    i_avg_a = ik_ka * 1000 * (1 + fault_margin_pct / 100)
    s_min = (i_avg_a * math.sqrt(fault_duration_sec)) / k_value

    candidates = [s for s in sorted(cable_sizes) if s * n_sets >= s_min]
    chosen_size = candidates[0] if candidates else None
    total_area = chosen_size * n_sets if chosen_size else None
    satisfied = chosen_size is not None

    steps = [
        {"step": "1", "desc": f"ฐานคำนวณ = {base_label} kVA", "value": f"{base_kva:,.1f} kVA"},
        {"step": "2", "desc": "I_rated = kVA×1000 / (√3 × V)", "value": f"{i_rated:,.1f} A"},
        {"step": "3", "desc": f"Fault Level, Ik = I_rated / (%Z/100)  [%Z={pct_z:.1f}%]",
         "value": f"{ik_ka:,.2f} kA"},
        {"step": "4", "desc": f"Average Fault Current, I = Ik × (1+margin)  [margin={fault_margin_pct:.0f}%]",
         "value": f"{i_avg_a/1000:,.2f} kA"},
        {"step": "5", "desc": f"Minimum size, S = I×√t / k  [t={fault_duration_sec}s, k={k_value}]",
         "value": f"{s_min:,.1f} sq.mm."},
        {"step": "6", "desc": f"Design size = {n_sets} set(s) × standard size",
         "value": f"{n_sets} x {chosen_size:.0f} sq.mm. = {total_area:,.0f} sq.mm." if chosen_size
                   else "❌ ไม่มีขนาดรองรับ — เพิ่ม set หรือขยาย standard size list"},
    ]

    return {
        "base_kva": base_kva,
        "base_source": base_label,
        "i_rated_a": i_rated,
        "ik_ka": ik_ka,
        "i_avg_a": i_avg_a,
        "s_min_sqmm": s_min,
        "n_sets": n_sets,
        "chosen_size": chosen_size,
        "total_area_sqmm": total_area,
        "satisfied": satisfied,
        "steps": steps,
    }


def compute_ground_cable_dual(
    trafo_kva: float,
    gen_kw: float,
    gen_pf: float,
    voltage: float,
    pct_z: float,
    fault_margin_pct: float,
    fault_duration_sec: float,
    k_value: float,
    cable_sizes: list,
    n_sets: int,
) -> dict:
    """
    คำนวณขนาดสายดิน BS 7671 แยก 2 ฐาน (ยืนยันโดยผู้ใช้ 2026-09 — เดิมเคยใช้ฐานเดียว max(trafo,gen)):
    - "trafo": ใช้ฐาน Transformer kVA → สำหรับ RMU_S_GROUNDCABLE, TX_S_GROUNDCABLE
    - "gen"  : ใช้ฐาน Generator kW/pf (แปลงเป็น kVA) → สำหรับ GEN_S_GROUNDCABLE, PTU_GROUNDCABLE
    คืน {"trafo": {...ผลลัพธ์เดี่ยว...}, "gen": {...ผลลัพธ์เดี่ยว...}}
    """
    gen_kva_equiv = gen_kw / gen_pf if gen_pf else 0.0

    trafo_result = _compute_ground_cable_single(
        trafo_kva, "Transformer", voltage, pct_z, fault_margin_pct,
        fault_duration_sec, k_value, cable_sizes, n_sets,
    )
    gen_result = _compute_ground_cable_single(
        gen_kva_equiv, "Generator", voltage, pct_z, fault_margin_pct,
        fault_duration_sec, k_value, cable_sizes, n_sets,
    )
    return {"trafo": trafo_result, "gen": gen_result}


def format_groundcable_text(default_text: str, n_sets: int, chosen_size: float) -> str:
    """
    แทนที่ขนาดสายในข้อความ default ด้วยผลคำนวณใหม่ รองรับ 2 รูปแบบ:
    1) 'NxSIZE' เช่น TX/GEN/PTU_GROUNDCABLE -> 'IEC01 2x240 Sq.mm. ...'
    2) เลขเดี่ยวหน้า 'Sq.mm.' เช่น RMU_S_GROUNDCABLE -> 'IEC01 240 Sq.mm. ...'
       (จะถูกอัปเกรดให้เป็น 'NxSIZE' เหมือนกันเมื่อ n_sets > 1)
    คงส่วนอื่น (conduit ⌀ ฯลฯ) ไว้เหมือนเดิมเพราะไม่มีสูตรคำนวณ
    ถ้าหา pattern ไม่เจอเลย จะคืนค่า default text เดิม (ให้ผู้ใช้แก้ manual เอง)
    """
    if chosen_size is None:
        return default_text
    new_frag = f"{n_sets}x{chosen_size:.0f}" if n_sets > 1 else f"{chosen_size:.0f}"

    # ลองรูปแบบ NxSIZE ก่อน (TX/GEN/PTU)
    result, n = re.subn(r"\d+x\d+", new_frag, default_text)
    if n > 0:
        return result

    # ถ้าไม่เจอ ลองรูปแบบเลขเดี่ยวหน้า Sq.mm. (RMU)
    result, n = re.subn(r"\d+(?=\s*Sq\.mm)", new_frag, default_text)
    if n > 0:
        return result

    return default_text