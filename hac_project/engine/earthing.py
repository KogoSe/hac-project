"""
ENGINE — Earthing / Ground Cable Sizing (BS 7671, Table 43A: S = I*sqrt(t)/k)
แยกออกจาก UI ชัดเจน ไม่มี st. ใดๆ ในไฟล์นี้

หลักการ (ตามที่ตกลงกันไว้):
- ใช้ kVA ตัวที่ "มากกว่า" ระหว่าง Transformer กับ Generator (แปลง kW→kVA ด้วย gen_pf)
  มาเป็นฐานคำนวณ Fault Level เดียว แล้วใช้ผลลัพธ์เดียวกันกับทั้ง 3 จุด
  (TX_S_GROUNDCABLE, GEN_S_GROUNDCABLE, PTU_GROUNDCABLE)
- Fault Level (Ik) มาจาก %Z ของหม้อแปลง/เครื่องกำเนิด (ไม่ใช้ network impedance เต็มรูปแบบ)
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


def compute_ground_cable(
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
    คำนวณขนาดสายดินตาม BS 7671 (S = I*sqrt(t)/k)
    ใช้ค่า kVA ที่มากกว่าระหว่าง Transformer กับ Generator (แปลงเป็น kVA เดียวกัน) เป็นฐาน
    คืน dict step-by-step + ผลลัพธ์สุดท้าย (ใช้ทั้งแสดงผลและ auto-fill)
    """
    gen_kva_equiv = gen_kw / gen_pf if gen_pf else 0.0
    base_kva = max(trafo_kva, gen_kva_equiv)
    base_source = "Transformer" if trafo_kva >= gen_kva_equiv else "Generator"

    i_rated = compute_full_load_current(base_kva, voltage)
    ik_ka = i_rated / (pct_z / 100) / 1000
    i_avg_a = ik_ka * 1000 * (1 + fault_margin_pct / 100)
    s_min = (i_avg_a * math.sqrt(fault_duration_sec)) / k_value

    candidates = [s for s in sorted(cable_sizes) if s * n_sets >= s_min]
    chosen_size = candidates[0] if candidates else None
    total_area = chosen_size * n_sets if chosen_size else None
    satisfied = chosen_size is not None

    steps = [
        {"step": "1", "desc": f"ฐานคำนวณ = max(Trafo kVA, Gen kW/pf) → ใช้ {base_source}",
         "value": f"{base_kva:,.1f} kVA"},
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
        "base_source": base_source,
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


def format_groundcable_text(default_text: str, n_sets: int, chosen_size: float) -> str:
    """
    แทนที่ส่วน 'NxSIZE' ในข้อความ default (เช่น 'IEC01 2x240 Sq.mm. IN PVC %%C80 mm.')
    ด้วยขนาดที่คำนวณได้ใหม่ คงส่วนอื่น (conduit ⌀ ฯลฯ) ไว้เหมือนเดิมเพราะไม่มีสูตรคำนวณ
    ถ้าหา pattern ไม่เจอ จะคืนค่า default text เดิม (ให้ผู้ใช้แก้ manual เอง)
    """
    if chosen_size is None:
        return default_text
    new_frag = f"{n_sets}x{chosen_size:.0f}"
    result, n = re.subn(r"\d+x\d+", new_frag, default_text)
    if n == 0:
        return default_text
    return result
