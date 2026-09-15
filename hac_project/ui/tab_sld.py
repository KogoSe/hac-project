"""
TAB 4: SLD ATTRIBUTES — กรอก/แก้ไข Attribute แล้วสร้าง Single Line Diagram (.dxf)

หมายเหตุสำหรับงานต่อไป: ถ้าต้องการดึงค่าที่คำนวณไว้จาก tab 3 (Equipment Sizing)
มาใช้ในนี้ (เช่น auto-fill ขนาด Transformer/Generator/Busway ลงใน PTU_FIX
attributes) ให้อ่านจาก:
    st.session_state.sizing_cfg           -> assumption/config ล่าสุด (ใช้ร่วมกันทุกกลุ่ม)
    st.session_state.sizing_group_calcs   -> list ของ {"gi", "chain", "equip"} ต่อกลุ่ม
                                              (source of truth — แต่ละกลุ่มเลือกขนาดของตัวเองอิสระกัน
                                              "group ใครกลุ่มมัน" ไม่ unify ข้ามกลุ่มแล้ว)
ทั้งหมดนี้ถูก set ไว้แล้วตอน render ของ ui/tab_sizing.py (ต้องเปิด tab 3 ก่อนอย่างน้อย 1 ครั้ง
ในเซสชันนั้น ค่าถึงจะมี — ควร guard ด้วย st.session_state.get(...) เสมอ)

gen_pf (Generator PF สำหรับแปลง kW→kVA) sync กับ tab "สรุปการคำนวณ Attribute"
(ui/tab_attribute_summary.py) แล้ว — อ่านจาก st.session_state.ground_cfg["gen_pf"]
ไม่ hardcode แยกอีกต่อไป (ดู compute_smart_ptu_fix_defaults ด้านล่าง)
"""
import streamlit as st

from constants import PTU_FIX_DEFAULTS, MDBAUX_DEFAULTS, SPARE_DEFAULTS
from engine.sizing import select_gen_busbar, select_rmu_attributes

import build_ptu_sldA


def build_feeder_list(state: dict) -> list:
    """แปลง mdbaux + spare → FEEDER_LIST format ที่ script ต้องการ"""
    feeder_list = []
    for _, val in state["mdbaux"]:
        feeder_list.append({"type": "MDBAUX", "label": val})
    for _, val in state["spare"]:
        feeder_list.append({"type": "SPARE", "label": val})
    return feeder_list


def build_overrides(state: dict) -> dict:
    """แปลง ptu_fix → PTU_FIX_OVERRIDES เฉพาะตัวที่ต่างจาก default"""
    default_dict = {name: val for name, val in PTU_FIX_DEFAULTS}
    return {
        name: val
        for name, val in state["ptu_fix"]
        if val != default_dict.get(name, "")
    }
#เชื่อมระบบ
def compute_smart_ptu_fix_defaults(gi: int) -> dict:
    """
    สร้างค่า default อัจฉริยะจากผลคำนวณ Equipment Sizing (tab 3) ของกลุ่ม gi เดียว
    (แต่ละกลุ่มเลือกขนาดของตัวเองอิสระกัน — "group ใครกลุ่มมัน" ไม่ unify ข้ามกลุ่มแล้ว)
    คืน dict ว่างถ้ายังไม่เคยเปิด tab 3 ในเซสชันนี้ (หรือไม่มีกลุ่ม gi) → fallback เป็นค่า default เดิมทั้งหมด

    gi : เลข generator group (1-based) ที่กำลังเลือกอยู่
    """
    group_calcs = st.session_state.get("sizing_group_calcs")
    if not group_calcs or gi < 1 or gi > len(group_calcs):
        return {}

    equip = group_calcs[gi - 1]["equip"]
    required_keys = ("ups", "gen", "trafo", "busway", "it_busbar", "before_ups_busbar")
    if any(equip.get(k, {}).get("size") is None for k in required_keys):
        return {}

    ups_kw    = equip["ups"]["size"]
    trafo_kva = equip["trafo"]["size"]
    gen_kw    = equip["gen"]["size"]
    busway_a  = equip["busway"]["size"]
    it_a      = equip["it_busbar"]["size"]
    preups_a  = equip["before_ups_busbar"]["size"]

    # gen_pf: ยึดตาม input ที่ผู้ใช้กรอกจริงใน tab "สรุปการคำนวณ Attribute" (หัวข้อ Ground Cable Assumption)
    # ไม่ hardcode แยกอีกต่อไป (เดิมเคยใช้ GEN_PF_ASSUMED = 0.8 คนละตัวกับ ground cable — ทำให้ไม่ sync กัน)
    # ถ้ายังไม่เคยเปิด tab สรุปฯ ในเซสชันนี้เลย fallback = 0.8 ไปก่อน
    GEN_PF_FALLBACK = 0.8
    gen_pf = st.session_state.get("ground_cfg", {}).get("gen_pf", GEN_PF_FALLBACK)

    trafo_mva = trafo_kva / 1000
    gen_mw    = gen_kw / 1000
    gen_mva   = gen_mw / gen_pf

    # GEN_S_BUSBARRATING / GEN_LEFT_ACB / GEN_RIGHT_ACB: คำนวณจากกระแส rated ของ Generator เอง
    # (ไม่ใช่ busway design ampere ของ PTU เหมือนเดิม) — ไม่เผื่อ Design Margin (ยืนยันโดยผู้ใช้)
    # เลือก standard size ตัวถัดไปที่ >= rated เสมอ — ใช้ voltage/busway_sizes ชุดเดียวกับจุดอื่นในระบบ
    sizing_cfg = st.session_state.get("sizing_cfg", {})
    gen_busbar_cfg = {
        "voltage":      sizing_cfg.get("voltage", 415.0),
        "busway_sizes": sizing_cfg.get("busway_sizes", [800, 1600, 2000, 2500, 3200, 4000, 5000]),
    }
    gen_busbar = select_gen_busbar(gen_kw, gen_pf, gen_busbar_cfg)
    gen_busbar_a = gen_busbar["size"] if gen_busbar["size"] is not None else busway_a

        # RMU / MV Ring — 4 attribute ท้าย (ยืนยันโดยผู้ใช้ 2026-09)
    # mv_voltage มาจาก tab "สรุปการคำนวณ Attribute" (Section 0) — ถ้ายังไม่เคยเปิด fallback = 22kV
    rmu_cfg    = st.session_state.get("rmu_cfg", {})
    mv_voltage = rmu_cfg.get("mv_voltage", 22000)
    rmu_sizes  = rmu_cfg.get("rmu_sizes", [200, 630])
    rmu = select_rmu_attributes(trafo_kva, mv_voltage, rmu_sizes)
    rmu_cb_str     = f"{rmu['rmu_cb']:.0f}"     if rmu["rmu_cb"]     else "N/A"
    rmu_busbar_str = f"{rmu['rmu_busbar']:.0f}" if rmu["rmu_busbar"] else "N/A"

    return {
        "UPS_RATING":          f"{ups_kw:.0f}kW",
        "TX_S_RATING":         f"{trafo_mva:.2f} MVA DRY TYPE (IP00) 22/0.4 kV, K-4 RATED,\nAL/AL 3P,4W, DYN11, %UK6, 50Hz",
        "GEN_S_RATING":        f"{gen_mw:.1f}MW/{gen_mva:.1f}MVA 400V,3%%C, 50Hz GENERATOR",

        "TX_S_BUSWAY":         f"{busway_a:.0f}A BUSWAY AL. IP 55 (BY PTU)",
        "GEN_S_BASWAYTOPTU":   f"{busway_a:.0f}A BUSWAY AL. IP 68",
        "PTU_MAINBUSBAR":      f"{busway_a:.0f}A CU, BUS BAR 100%N, 25%G, 3P 4W",
        "GEN_S_BUSBARRATING":  f"{gen_busbar_a:.0f}A CU, BUS BAR 100%N, 25%G, 3P 4W",
        "PTU_IF01":            f"{busway_a:.0f}AT\n{busway_a:.0f}AF\n4P, ACB\nLSI (NC)",
        "PTU_IF02":            f"{gen_busbar_a:.0f}AT\n{gen_busbar_a:.0f}AF\n4P, ACB\nLSI (NO)",
        "GEN_LEFT_ACB":        f"{gen_busbar_a:.0f}AT\n{gen_busbar_a:.0f}AF\n4P, ACB,\nLSI (NC)",
        "GEN_RIGHT_ACB":       f"{gen_busbar_a:.0f}AT\n{gen_busbar_a:.0f}AF\n4P, ACB,\nLSI (NO)",

        "PTU_BUSBARBEFOREUPS": f"{preups_a:.0f}A CU, BUS BAR 100%N, 25%G, 3P 4W",

        "FINALBUSBAR01":       f"{it_a:.0f}A BUSWAY AL. IP 68",
        "FINALBUSBAR02":       f"{it_a:.0f}A BUSWAY AL. IP 68",
        "FINALBUSBAR03":       f"{it_a:.0f}A BUSWAY AL. IP 68",
        "OUPS_MAINITBUSBAR":   f"{it_a:.0f}A CU, BUS BAR 100%N, 25%G, 3P 4W",
        "OUPS_ITBUSBAR_IF02":  f"{it_a:.0f}A CU, BUS BAR 100%N, 25%G, 3P 4W",
        "OUPS_CB_ITOF01":      f"{it_a:.0f}AT\n{it_a:.0f}AF\nTPN, ACB,\nLSI (NC)",
        "OUPS_CB_ITOF02":      f"{it_a:.0f}AT\n{it_a:.0f}AF\nTPN, ACB,\nLSI (NC)",
        "OUPS_CB_ITIF01":      f"{it_a:.0f}AT\n{it_a:.0f}AF\n4P, ACB\nLSI (NO)",
        "OUPS_CB_ITIF02":      f"{it_a:.0f}AT\n{it_a:.0f}AF\nTPN, ACB\nLSI (NC)",
        "OUPS_CB_ITIF03":      f"{it_a:.0f}AT\n{it_a:.0f}AF\nTPN,ACB,\nLSI (NO)",

        # CB_BUSBARBEFOREUPS = เท่ากับ before_ups_busbar (ยืนยันโดยผู้ใช้: เลือกเท่า CB ของ busbar เดียวกัน)
        "CB_BUSBARBEFOREUPS":  f"{preups_a:.0f}AT\n{preups_a:.0f}AF\n4P, ACB\nLSI (NC)",

        "RMU_CB":              rmu_cb_str,
        "RMU_BUSBAR":          f"CU BUSBAR {rmu_busbar_str}A",
        "RMU_LEFT_CB":         rmu_busbar_str,
        "RMU_RIGHT_LB":        rmu_busbar_str,
    }


def apply_ground_cable_defaults(smart_defaults: dict, gi: int) -> dict:
    """
    เติมค่า ground cable เข้า smart_defaults จากผลคำนวณ 2 ฐานแยกกัน ของกลุ่ม gi เดียว
    (st.session_state.ground_result = {gi: {"trafo": {...}, "gen": {...}}, ...} — per-group,
    เก็บโดย ui/tab_attribute_summary.py):
    - ฐาน Transformer -> RMU_S_GROUNDCABLE, TX_S_GROUNDCABLE
    - ฐาน Generator   -> GEN_S_GROUNDCABLE, PTU_GROUNDCABLE
    ไม่กระทบ logic เดิมถ้ายังไม่เคยเปิด tab สรุป Attribute Calculation ของกลุ่มนี้ (fallback เป็น default เดิม)
    """
    ground_all = st.session_state.get("ground_result") or {}
    ground = ground_all.get(gi)
    if not ground:
        return smart_defaults

    from constants import PTU_FIX_DEFAULTS
    from engine.earthing import format_groundcable_text

    default_dict = {name: val for name, val in PTU_FIX_DEFAULTS}

    trafo_res = ground.get("trafo", {})
    if trafo_res.get("satisfied"):
        for tag in ("RMU_S_GROUNDCABLE", "TX_S_GROUNDCABLE"):
            smart_defaults[tag] = format_groundcable_text(
                default_dict[tag], trafo_res["n_sets"], trafo_res["chosen_size"])

    gen_res = ground.get("gen", {})
    if gen_res.get("satisfied"):
        for tag in ("GEN_S_GROUNDCABLE", "PTU_GROUNDCABLE"):
            smart_defaults[tag] = format_groundcable_text(
                default_dict[tag], gen_res["n_sets"], gen_res["chosen_size"])

    return smart_defaults

def render():
    st.header("📐 SLD Attributes")
    st.caption("กรอก/แก้ไข Attribute สำหรับสร้าง Single Line Diagram | ค่า default ตามรูปแบบมาตรฐาน")

    # ── เลือกกลุ่ม Generator ────────────────────────────────────
    n_grp = st.session_state.get("n_groups", 3)
    grp_options = [f"Group {i}" for i in range(1, n_grp + 1)]
    selected_grp = st.selectbox("เลือก Generator Group", options=grp_options, key="sld_grp_select")
    grp_key = selected_grp.replace(" ", "_").lower()  # เช่น "group_1"
    gi = grp_options.index(selected_grp) + 1

    # init session state สำหรับแต่ละกลุ่ม
    if "sld_attrs" not in st.session_state:
        st.session_state.sld_attrs = {}

    if grp_key not in st.session_state.sld_attrs:
        # init ด้วย default values
        smart_defaults = compute_smart_ptu_fix_defaults(gi)
        smart_defaults = apply_ground_cable_defaults(smart_defaults, gi)
        st.session_state.sld_attrs[grp_key] = {
            "ptu_fix":  [(name, smart_defaults.get(name, val)) for name, val in PTU_FIX_DEFAULTS],  # ← แก้บรรทัดนี้
            "mdbaux_count": 1,
            "mdbaux":   [(name, val) for name, val in MDBAUX_DEFAULTS],
            "spare_count":  1,
            "spare":    [(name, val) for name, val in SPARE_DEFAULTS],
            
        }
        if not smart_defaults:                                    # ← เพิ่มตรงนี้ ย่อเท่ากับบรรทัดบน
            st.info("ℹ️ ยังไม่พบผลคำนวณจาก tab Equipment Sizing — ใช้ค่า default พื้นฐานไปก่อน (เปิด tab 3 ก่อนแล้วกลับมาที่นี่ใหม่เพื่อ auto-fill)")
        elif "ground_cfg" not in st.session_state:
            st.caption(
                "⚠️ ยังไม่เคยเปิด tab 'สรุปการคำนวณ Attribute' ในเซสชันนี้ — ใช้ Generator PF=0.80 "
                "(ค่าเริ่มต้น) ไปก่อนสำหรับ GEN_S_RATING/GEN_S_BUSBARRATING/ACB ถ้าต้องการเปลี่ยน PF "
                "ให้ไปตั้งค่าที่ tab นั้นก่อน แล้วลบกลุ่มนี้ทิ้งเพื่อดึงค่าใหม่"
            )

    attr_state = st.session_state.sld_attrs[grp_key]

    # ── SECTION 1: PTU_FIX ──────────────────────────────────────
    with st.expander("🔧 PTU_FIX  (33 attributes)", expanded=True):
        st.caption("Block: PTU_FIX — แก้ค่าได้โดยตรง")

        updated_ptu = []
        for i, (attr_name, attr_val) in enumerate(attr_state["ptu_fix"]):
            col1, col2 = st.columns([2, 3])
            with col1:
                # attribute name แสดงเป็น label ไม่ให้แก้
                st.markdown(
                    f'<div style="padding:8px 4px;font-size:13px;font-family:monospace;'
                    f'color:#1F4E79;font-weight:500">{attr_name}</div>',
                    unsafe_allow_html=True,
                )
            with col2:
                new_val = st.text_input(
                    label=attr_name,           # label ซ่อนไว้ (ใช้ markdown แทน)
                    value=attr_val,
                    key=f"ptu_{grp_key}_{i}",
                    label_visibility="collapsed",
                )
            updated_ptu.append((attr_name, new_val))
        attr_state["ptu_fix"] = updated_ptu

    # ── SECTION 2: MDBAUX ───────────────────────────────────────
    with st.expander("🔌 MDBAUX", expanded=False):
        st.caption("Block: MDBAUX — กรอกจำนวน block และค่า CB")

        mdbaux_count = st.number_input(
            "จำนวน MDBAUX Block",
            min_value=1, max_value=20, step=1,
            value=attr_state["mdbaux_count"],
            key=f"mdbaux_count_{grp_key}",
        )
        attr_state["mdbaux_count"] = int(mdbaux_count)

        # ปรับ list ให้ตรงกับจำนวน
        current_mdbaux = attr_state["mdbaux"]
        default_val = MDBAUX_DEFAULTS[0][1]
        while len(current_mdbaux) < mdbaux_count:
            current_mdbaux.append(("CB_MCCB_BLOCK", default_val))
        current_mdbaux = current_mdbaux[:mdbaux_count]

        updated_mdbaux = []
        for i, (attr_name, attr_val) in enumerate(current_mdbaux):
            col1, col2 = st.columns([2, 3])
            with col1:
                st.markdown(
                    f'<div style="padding:8px 4px;font-size:13px;font-family:monospace;'
                    f'color:#1F4E79;font-weight:500">MDBAUX {i+1} — {attr_name}</div>',
                    unsafe_allow_html=True,
                )
            with col2:
                new_val = st.text_area(
                    label=f"mdbaux_{i}",
                    value=attr_val,
                    key=f"mdbaux_{grp_key}_{i}",
                    label_visibility="collapsed",
                    height=68,
                    help="พิมพ์ Enter เพื่อขึ้นบรรทัดใหม่ในแบบ",
                )
            updated_mdbaux.append((attr_name, new_val))
        attr_state["mdbaux"] = updated_mdbaux

    # ── SECTION 3: SPARE ────────────────────────────────────────
    with st.expander("🔲 SPARE", expanded=False):
        st.caption("Block: SPARE — กรอกจำนวน block และค่า CB")

        spare_count = st.number_input(
            "จำนวน SPARE Block",
            min_value=1, max_value=20, step=1,
            value=attr_state["spare_count"],
            key=f"spare_count_{grp_key}",
        )
        attr_state["spare_count"] = int(spare_count)

        current_spare = attr_state["spare"]
        default_spare_val = SPARE_DEFAULTS[0][1]
        while len(current_spare) < spare_count:
            current_spare.append(("CB_MCCB_BLOCK_SPARE", default_spare_val))
        current_spare = current_spare[:spare_count]

        updated_spare = []
        for i, (attr_name, attr_val) in enumerate(current_spare):
            col1, col2 = st.columns([2, 3])
            with col1:
                st.markdown(
                    f'<div style="padding:8px 4px;font-size:13px;font-family:monospace;'
                    f'color:#1F4E79;font-weight:500">SPARE {i+1} — {attr_name}</div>',
                    unsafe_allow_html=True,
                )
            with col2:
                new_val = st.text_area(
                    label=f"spare_{i}",
                    value=attr_val,
                    key=f"spare_{grp_key}_{i}",
                    label_visibility="collapsed",
                    height=68,
                    help="พิมพ์ Enter เพื่อขึ้นบรรทัดใหม่ในแบบ",
                )
            updated_spare.append((attr_name, new_val))
        attr_state["spare"] = updated_spare

    # ── SECTION 4: สร้าง SLD ────────────────────────────────────
    st.divider()
    st.subheader("🏗️ สร้าง Single Line Diagram")
    if st.button("🏗️ สร้าง SLD (.dxf)", type="primary", use_container_width=True):
        try:
            feeder_list   = build_feeder_list(attr_state)
            overrides     = build_overrides(attr_state)
            dxf_bytes     = build_ptu_sldA.run_from_streamlit(feeder_list, overrides)
            st.success(f"✅ สร้าง SLD สำเร็จ — {len(feeder_list)} feeder")
            st.download_button(
                label=f"⬇️ Download {selected_grp} SLD (.dxf)",
                data=dxf_bytes,
                file_name=f"ptu_sld_{grp_key}.dxf",
                mime="application/octet-stream",
                use_container_width=True,
            )

            try:
                pdf_bytes = build_ptu_sldA.export_pdf_from_dxf_bytes(dxf_bytes, paper_size="A3")
                st.download_button(
                    label=f"📄 Plot {selected_grp} เป็น PDF (A3, Landscape, Monochrome)",
                    data=pdf_bytes,
                    file_name=f"ptu_sld_{grp_key}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

            except Exception as e:
                st.warning(f"⚠️ สร้าง PDF ไม่สำเร็จ (ไฟล์ .dxf ยังใช้ได้ปกติ): {e}")
        except FileNotFoundError:
            st.error("❌ ไม่พบไฟล์ PTU_TEST.dxf — วางไฟล์ไว้ในโฟลเดอร์เดียวกับ app.py")
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาด: {e}")