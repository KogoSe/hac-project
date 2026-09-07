"""
TAB: สรุปการคำนวณ Attribute — โชว์ว่าแต่ละ attribute ใน PTU_FIX มาจากไหน/คำนวณยังไง
ก่อนถูกส่งไปที่ tab SLD Attributes (auto-fill ที่นั่นแล้ว — ยังแก้ manual ทับได้เหมือนเดิม)

Section 1: Ground Cable Sizing (BS 7671) — คำนวณสดในหน้านี้ ผลถูกเก็บใน
           st.session_state.ground_cfg / ground_result ให้ tab_sld อ่านไปใช้
Section 2: ตารางสรุปทุก attribute — คำนวณ / default พร้อมสูตร
"""
import streamlit as st
import pandas as pd

from constants import PTU_FIX_DEFAULTS
from engine.earthing import compute_ground_cable, TABLE_43A_K_VALUES
from ui.tab_sld import compute_smart_ptu_fix_defaults


def parse_sizes(s):
    try:
        return sorted([float(x.strip()) for x in s.split(",") if x.strip()])
    except Exception:
        return []


def render():
    st.header("🧮 สรุปการคำนวณ Attribute (PTU_FIX)")
    st.caption("โชว์ที่มาของทุก attribute ก่อนถูกนำไปใช้ใน tab SLD Attributes — แก้ manual ที่ tab SLD ได้เสมอถ้าไม่พอใจค่านี้")

    sizes = st.session_state.get("sizing_common_sizes")
    if not sizes or any(sizes.get(k) is None for k in ("trafo", "gen", "busway", "it_busbar", "before_ups_busbar")):
        st.info("ไปที่แท็บ **Equipment Sizing** ก่อนอย่างน้อย 1 ครั้ง เพื่อให้มีค่า kVA/kW/Ampere ให้คำนวณต่อ")
        st.stop()

    trafo_kva = sizes["trafo"]
    gen_kw    = sizes["gen"]

    # ═══════════════════════════════════════════════════════════
    # SECTION 1 — GROUND CABLE SIZING (BS 7671)
    # ═══════════════════════════════════════════════════════════
    st.subheader("1️⃣ Ground Cable Sizing — BS 7671  (S = I√t / k)")
    st.caption("ใช้ผลลัพธ์เดียวกันกับ TX_S_GROUNDCABLE / GEN_S_GROUNDCABLE / PTU_GROUNDCABLE ทั้ง 3 จุด "
               "(ใช้ kVA ที่มากกว่าระหว่าง Transformer กับ Generator เป็นฐานคำนวณเดียว)")

    with st.expander("⚙️ Assumption — Ground Cable", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            gen_pf = st.number_input("Generator PF (แปลง kW→kVA)", value=0.8, step=0.05,
                                      help="ใช้ค่าเดียวกับที่ tab SLD ใช้แปลง Generator kW→MVA")
            pct_z = st.number_input("%Z (Transformer/Generator)", value=6.0, step=0.5)
        with c2:
            fault_margin = st.number_input("Fault Current Margin (%)", value=10.0, step=1.0)
            fault_t = st.number_input("Fault Duration, t (sec)", value=0.3, step=0.1)
        with c3:
            k_label = st.selectbox("Conductor / Insulation (Table 43A)",
                                    options=list(TABLE_43A_K_VALUES.keys()), index=0)
            k_value = TABLE_43A_K_VALUES[k_label]
            st.caption(f"k = {k_value} A/sq.mm.")

        c4, c5 = st.columns(2)
        with c4:
            cable_sizes_str = st.text_input("Standard Cable Sizes (sq.mm.)",
                                             value="95,120,150,185,240,300,400")
        with c5:
            n_sets = st.number_input("จำนวน Sets (parallel run)", min_value=1, max_value=6, value=2, step=1)

    voltage = st.session_state.get("sizing_cfg", {}).get("voltage", 415.0)
    cable_sizes = parse_sizes(cable_sizes_str)

    ground_result = compute_ground_cable(
        trafo_kva=trafo_kva, gen_kw=gen_kw, gen_pf=gen_pf, voltage=voltage,
        pct_z=pct_z, fault_margin_pct=fault_margin, fault_duration_sec=fault_t,
        k_value=k_value, cable_sizes=cable_sizes, n_sets=int(n_sets),
    )
    # เก็บผลไว้ให้ tab_sld ดึงไปใช้ auto-fill 3 attribute
    st.session_state.ground_cfg = {
        "gen_pf": gen_pf, "pct_z": pct_z, "fault_margin": fault_margin,
        "fault_t": fault_t, "k_value": k_value, "cable_sizes": cable_sizes, "n_sets": int(n_sets),
    }
    st.session_state.ground_result = ground_result

    step_df = pd.DataFrame(ground_result["steps"])[["step", "desc", "value"]]
    step_df.columns = ["Step", "Description", "Value"]
    st.dataframe(step_df, use_container_width=True, hide_index=True)

    if ground_result["satisfied"]:
        st.success(
            f"✅ Design size = {ground_result['n_sets']} x {ground_result['chosen_size']:.0f} sq.mm. "
            f"(รวม {ground_result['total_area_sqmm']:,.0f} sq.mm.) "
            f"≥ Minimum required {ground_result['s_min_sqmm']:,.1f} sq.mm."
        )
    else:
        st.error(
            f"❌ ไม่มีขนาดสายในลิสต์ที่พอ — ต้องการ ≥ {ground_result['s_min_sqmm']:,.1f} sq.mm. "
            f"ลองเพิ่มจำนวน Sets หรือเพิ่มขนาดสายในลิสต์"
        )

    st.divider()

    # ═══════════════════════════════════════════════════════════
    # SECTION 2 — สรุปทุก Attribute (คำนวณ / default)
    # ═══════════════════════════════════════════════════════════
    st.subheader("2️⃣ สรุปที่มาของทุก Attribute (PTU_FIX)")

    smart_defaults = compute_smart_ptu_fix_defaults()

    # อธิบายสูตรของแต่ละ attribute ที่มาจาก Equipment Sizing (คำนวณไว้แล้วใน tab_sld.py)
    FORMULA_NOTES = {
        "UPS_RATING":          "จาก sizing_common_sizes['ups'] โดยตรง",
        "TX_S_RATING":         "kVA ของ Transformer → MVA",
        "GEN_S_RATING":        f"kW ของ Generator → MW/MVA (สมมติ PF={gen_pf:.2f})",
        "TX_S_BUSWAY":         "Design Ampere ของ PTU busway (จาก Load Chain, tab Equipment Sizing)",
        "GEN_S_BASWAYTOPTU":   "เดียวกับ TX_S_BUSWAY (busway design ampere)",
        "PTU_MAINBUSBAR":      "เดียวกับ busway design ampere",
        "GEN_S_BUSBARRATING":  "เดียวกับ busway design ampere",
        "PTU_IF01":            "เท่ากับ GEN busbar rating",
        "PTU_IF02":            "เท่ากับ TX busway rating",
        "GEN_LEFT_ACB":        "เลือกเท่า busbar (AT=AF)",
        "GEN_RIGHT_ACB":       "เลือกเท่า busbar (AT=AF)",
        "PTU_BUSBARBEFOREUPS": "Ampere หลัง UPS loss+charging ก่อน HVAC (before_ups_busbar)",
        "CB_BUSBARBEFOREUPS":  "เท่ากับ before_ups_busbar (เลือกเท่า CB ของ busbar เดียวกัน)",
        "CB_FROMGEN":          "เท่ากับ busway ของ Generator",
        "FINALBUSBAR01":       "Ampere ของ Connected IT Load ก่อนเข้า UPS (it_busbar)",
        "FINALBUSBAR02":       "เดียวกับ FINALBUSBAR01",
        "FINALBUSBAR03":       "เดียวกับ FINALBUSBAR01",
        "OUPS_MAINITBUSBAR":   "เดียวกับ it_busbar",
        "OUPS_ITBUSBAR_IF02":  "เดียวกับ it_busbar",
        "OUPS_CB_ITOF01":      "เลือกเท่า it_busbar (ยังไม่ยืนยันว่าหารครึ่งหรือเต็ม — ใช้เต็มไปก่อน)",
        "OUPS_CB_ITOF02":      "เดียวกับ OUPS_CB_ITOF01",
        "OUPS_CB_ITIF01":      "เดียวกับ it_busbar",
        "OUPS_CB_ITIF02":      "เดียวกับ it_busbar",
        "OUPS_CB_ITIF03":      "เดียวกับ it_busbar",
        "TX_S_GROUNDCABLE":    "BS 7671 — ดู Section 1 ด้านบน (Ground Cable Sizing)",
        "RMU_S_GROUNDCABLE":   "BS 7671 — เดียวกับ TX_S_GROUNDCABLE (ผลจาก Section 1 ด้านบน)",
        "GEN_S_GROUNDCABLE":   "BS 7671 — ดู Section 1 ด้านบน (Ground Cable Sizing)",
        "PTU_GROUNDCABLE":     "BS 7671 — ดู Section 1 ด้านบน (Ground Cable Sizing)",
    }

    ground = st.session_state.get("ground_result")
    if ground and ground.get("satisfied"):
        from engine.earthing import format_groundcable_text
        default_dict = {n: v for n, v in PTU_FIX_DEFAULTS}
        for tag in ("RMU_S_GROUNDCABLE", "TX_S_GROUNDCABLE", "GEN_S_GROUNDCABLE", "PTU_GROUNDCABLE"):
            smart_defaults[tag] = format_groundcable_text(default_dict[tag], ground["n_sets"], ground["chosen_size"])

    rows = []
    for tag, default_val in PTU_FIX_DEFAULTS:
        is_calc = tag in smart_defaults
        rows.append({
            "Attribute": tag,
            "ประเภท": "🟢 คำนวณ" if is_calc else "⚪ Default",
            "สูตร / ที่มา": FORMULA_NOTES.get(tag, "—") if is_calc else "ค่าคงที่ (ยังไม่มีสูตร)",
            "ค่าที่จะถูกส่งไป SLD": (smart_defaults[tag] if is_calc else default_val).replace("\n", " / "),
        })

    df = pd.DataFrame(rows)
    n_calc = (df["ประเภท"] == "🟢 คำนวณ").sum()
    st.caption(f"คำนวณอัตโนมัติ {n_calc} / {len(df)} attribute — ที่เหลือเป็นค่า default (แก้ manual ที่ tab SLD ได้)")
    st.dataframe(df, use_container_width=True, hide_index=True, height=600)

    st.info(
        "ℹ️ ค่าทั้งหมดในตารางนี้เป็น **preview** เท่านั้น การ auto-fill จริงเกิดขึ้นที่ tab "
        "**SLD Attributes** ตอนเปิดกลุ่มนั้นครั้งแรกในเซสชัน — ถ้าเคยเปิดไปแล้วและมีการแก้ manual "
        "ทับไว้ ค่าที่ tab SLD จะไม่ถูกเขียนทับซ้ำโดยอัตโนมัติ ต้องลบ/รีเซ็ต group นั้นถ้าต้องการดึงค่าใหม่"
    )