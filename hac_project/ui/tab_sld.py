"""
TAB 4: SLD ATTRIBUTES — กรอก/แก้ไข Attribute แล้วสร้าง Single Line Diagram (.dxf)

หมายเหตุสำหรับงานต่อไป: ถ้าต้องการดึงค่าที่คำนวณไว้จาก tab 3 (Equipment Sizing)
มาใช้ในนี้ (เช่น auto-fill ขนาด Transformer/Generator/Busway ลงใน PTU_FIX
attributes) ให้อ่านจาก:
    st.session_state.sizing_cfg           -> assumption/config ล่าสุด
    st.session_state.sizing_group_calcs   -> list ของ {"gi", "chain", "equip"} ต่อกลุ่ม
    st.session_state.sizing_common_sizes  -> {"ups":.., "gen":.., "trafo":.., "busway":..}
ทั้งหมดนี้ถูก set ไว้แล้วตอน render ของ ui/tab_sizing.py (ต้องเปิด tab 3 ก่อนอย่างน้อย 1 ครั้ง
ในเซสชันนั้น ค่าถึงจะมี — ควร guard ด้วย st.session_state.get(...) เสมอ)
"""
import streamlit as st

from constants import PTU_FIX_DEFAULTS, MDBAUX_DEFAULTS, SPARE_DEFAULTS

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


def render():
    st.header("📐 SLD Attributes")
    st.caption("กรอก/แก้ไข Attribute สำหรับสร้าง Single Line Diagram | ค่า default ตามรูปแบบมาตรฐาน")

    # ── เลือกกลุ่ม Generator ────────────────────────────────────
    n_grp = st.session_state.get("n_groups", 3)
    grp_options = [f"Group {i}" for i in range(1, n_grp + 1)]
    selected_grp = st.selectbox("เลือก Generator Group", options=grp_options, key="sld_grp_select")
    grp_key = selected_grp.replace(" ", "_").lower()  # เช่น "group_1"

    # init session state สำหรับแต่ละกลุ่ม
    if "sld_attrs" not in st.session_state:
        st.session_state.sld_attrs = {}

    if grp_key not in st.session_state.sld_attrs:
        # init ด้วย default values
        st.session_state.sld_attrs[grp_key] = {
            "ptu_fix":  [(name, val) for name, val in PTU_FIX_DEFAULTS],
            "mdbaux_count": 1,
            "mdbaux":   [(name, val) for name, val in MDBAUX_DEFAULTS],
            "spare_count":  1,
            "spare":    [(name, val) for name, val in SPARE_DEFAULTS],
        }

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
                new_val = st.text_input(
                    label=f"mdbaux_{i}",
                    value=attr_val,
                    key=f"mdbaux_{grp_key}_{i}",
                    label_visibility="collapsed",
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
                new_val = st.text_input(
                    label=f"spare_{i}",
                    value=attr_val,
                    key=f"spare_{grp_key}_{i}",
                    label_visibility="collapsed",
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
        except FileNotFoundError:
            st.error("❌ ไม่พบไฟล์ PTU_TEST.dxf — วางไฟล์ไว้ในโฟลเดอร์เดียวกับ app.py")
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาด: {e}")
