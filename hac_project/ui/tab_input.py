"""
TAB 1: INPUT — กรอกข้อมูล HAC
"""
import streamlit as st
import pandas as pd
import os
import openpyxl

from constants import SOURCE_OPTIONS, N_UPS_PER_GROUP_OPTIONS, get_group_ups_units
from engine.optimization import DEFAULT_TIME_LIMIT
from engine.pairing import parse_rack_layout
from engine.sizing import suggest_group_configs
from ui.svg_diagram import build_hac_svg

EXCEL_IMPORT_PATH = "Input_datahall.xlsx"  # วางไว้ที่ hac_project/ (ระดับเดียวกับ app.py)


def load_hac_df_from_excel(sheet_name: str) -> tuple[pd.DataFrame, list[str]]:
    """
    อ่าน sheet ที่เลือกจาก Input_datahall.xlsx → DataFrame รูปแบบเดียวกับ hac_df
    โครงสร้างไฟล์ใหม่: แถว 1 = header, แถว 2 เป็นต้นไป = ข้อมูล (1 Excel row = 1 df row จริง ไม่ derive/duplicate เพิ่ม)
    คอลัมน์ A = HAC Name, B = Side (บน/ล่าง), C = Source Type, D เป็นต้นไป = Rack Layout values
    Side ว่าง → default "บน" (คืนรายชื่อ HAC ที่ไม่ได้ระบุ Side กลับมาด้วย ให้ UI แสดง warning)
    """
    wb = openpyxl.load_workbook(EXCEL_IMPORT_PATH, data_only=True)
    ws = wb[sheet_name]

    rows_out = []
    missing_side = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        name = row[0]
        source = row[2]
        if name is None or source is None:
            continue  # แถวว่าง ข้ามไป
        side = row[1]
        if side is None or str(side).strip() == "":
            side = "บน"
            missing_side.append(str(name))
        rack_values = [v for v in row[3:] if v is not None]
        rack_str = ", ".join(str(int(v)) if float(v).is_integer() else str(v) for v in rack_values)
        rows_out.append({
            "HAC Name": str(name),
            "Side": str(side),
            "Rack Layout (kW)": rack_str,
            "Source Type": str(source),
        })

    return pd.DataFrame(rows_out), missing_side


def render():
    st.header("กรอกข้อมูล HAC")
    st.caption("แต่ละ HAC มีได้ 1-2 แถว (บน/ล่าง) — กรอกทีละแถวจริง ไม่มี mirror อัตโนมัติ | Source Type: 2-source (default) หรือ 4-source สำหรับ Liquid rack ≥100 kW")

    if st.session_state.get("excel_import_warning"):
        st.warning(st.session_state.excel_import_warning)

 # ── SECTION: Import จาก Excel ────────────────────────────
    with st.expander("📥 Import ข้อมูลจาก Excel", expanded=False):
        if os.path.exists(EXCEL_IMPORT_PATH):
            try:
                sheet_names = openpyxl.load_workbook(EXCEL_IMPORT_PATH, read_only=True).sheetnames
                col1, col2 = st.columns([3, 1])
                with col1:
                    selected_sheet = st.selectbox("เลือก Sheet", options=sheet_names, key="excel_sheet_select")
                with col2:
                    st.write(""); st.write("")
                    if st.button("📥 โหลดข้อมูล", use_container_width=True, type="primary"):
                        new_df, missing_side = load_hac_df_from_excel(selected_sheet)
                        if len(new_df) == 0:
                            st.warning(f"⚠️ ไม่พบข้อมูลใน sheet '{selected_sheet}'")
                        else:
                            st.session_state.hac_df = new_df   # ทับตารางเดิมทั้งหมด
                            if missing_side:
                                st.session_state.excel_import_warning = (
                                    f"⚠️ พบแถวที่ไม่ได้ระบุ Side (ใช้ค่า default 'บน'): {', '.join(missing_side)}"
                                )
                            else:
                                st.session_state.excel_import_warning = None
                            st.success(f"✅ โหลด {len(new_df)} แถวจาก sheet '{selected_sheet}' แล้ว")
                            st.rerun()
            except Exception as e:
                st.error(f"❌ อ่านไฟล์ไม่สำเร็จ: {e}")
        else:
            st.info(f"ℹ️ ไม่พบไฟล์ `{EXCEL_IMPORT_PATH}` — วางไฟล์ไว้ในโฟลเดอร์เดียวกับ app.py แล้ว rerun ใหม่")

    st.divider()

    # default data — 1 sheet row = 1 แถวจริง (long format) ค่าบน/ล่างเท่าเดิมเพื่อหน้าตา default ไม่เปลี่ยน
    if "hac_df" not in st.session_state:
        st.session_state.hac_df = pd.DataFrame([
            {"HAC Name": "HAC 1", "Side": "บน",   "Rack Layout (kW)": "20, 20, 20, 20, 20, 20, 20, 20, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 1", "Side": "ล่าง", "Rack Layout (kW)": "20, 20, 20, 20, 20, 20, 20, 20, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 2", "Side": "บน",   "Rack Layout (kW)": "20, 20, 20, 20, 20, 20, 20, 20, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 2", "Side": "ล่าง", "Rack Layout (kW)": "20, 20, 20, 20, 20, 20, 20, 20, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 3", "Side": "บน",   "Rack Layout (kW)": "20, 150, 150, 150, 150, 150, 150, 150, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 3", "Side": "ล่าง", "Rack Layout (kW)": "20, 150, 150, 150, 150, 150, 150, 150, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 4", "Side": "บน",   "Rack Layout (kW)": "20, 150, 150, 150, 150, 150, 150, 150, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 4", "Side": "ล่าง", "Rack Layout (kW)": "20, 150, 150, 150, 150, 150, 150, 150, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 5", "Side": "บน",   "Rack Layout (kW)": "20, 150, 150, 150, 150, 150, 150, 150, 20, 20", "Source Type": "2-source"},
            {"HAC Name": "HAC 5", "Side": "ล่าง", "Rack Layout (kW)": "20, 150, 150, 150, 150, 150, 150, 150, 20, 20", "Source Type": "2-source"},
        ])

    # migrate df เก่าที่ยังใช้ Rack Count + Load per Rack
    df_cols = st.session_state.hac_df.columns.tolist()
    if "Rack Layout (kW)" not in df_cols and "Rack Count" in df_cols:
        old = st.session_state.hac_df
        st.session_state.hac_df = pd.DataFrame([
            {
                "HAC Name":        r["HAC Name"],
                "Rack Layout (kW)": ", ".join([str(int(r["Load per Rack (kW)"]))] * int(r["Rack Count"])),
                "Source Type":     r.get("Source Type", "2-source"),
            }
            for _, r in old.iterrows()
        ])
    if "Source Type" not in st.session_state.hac_df.columns:
        st.session_state.hac_df["Source Type"] = "2-source"

    # migrate session state เก่าที่ยังไม่มีคอลัมน์ Side: duplicate แต่ละแถวเดิมเป็นบน+ล่าง 1 ครั้ง (ทำครั้งเดียว)
    if "Side" not in st.session_state.hac_df.columns:
        old = st.session_state.hac_df
        new_rows = []
        for _, r in old.iterrows():
            for side in ("บน", "ล่าง"):
                new_rows.append({
                    "HAC Name":         r["HAC Name"],
                    "Side":             side,
                    "Rack Layout (kW)": r["Rack Layout (kW)"],
                    "Source Type":      r.get("Source Type", "2-source"),
                })
        st.session_state.hac_df = pd.DataFrame(new_rows)

    # เรียงคอลัมน์ให้ตรง data model ใหม่
    st.session_state.hac_df = st.session_state.hac_df[["HAC Name", "Side", "Rack Layout (kW)", "Source Type"]]

    edited_df = st.data_editor(
        st.session_state.hac_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "HAC Name": st.column_config.TextColumn("HAC Name", required=True),
            "Side": st.column_config.SelectboxColumn(
                "Side",
                options=["บน", "ล่าง"],
                required=True,
                help="HAC เดียวกันต้องอยู่แถวติดกัน มีได้สูงสุด 2 แถว และ Side ห้ามซ้ำกัน",
            ),
            "Rack Layout (kW)": st.column_config.TextColumn(
                "Rack Layout (kW)",
                required=True,
                help="กรอกขนาด kW ของแต่ละตู้คั่นด้วยจุลภาค เช่น: 20, 150, 150, 150, 20",
            ),
            "Source Type": st.column_config.SelectboxColumn(
                "Source Type",
                options=SOURCE_OPTIONS,
                required=True,
                help="2-source = Dual-cord (จ่ายจาก 2 UPS) | 4-source = เสียบ 4 เส้นจริงทางกายภาพเสมอ "
                     "(ถ้ากลุ่มมี UPS มากกว่า 4 ตัว MILP จะเลือกว่าเสียบเข้า 4 ตัวไหน)",
            ),
        },
        key="hac_editor",
    )
    st.session_state.hac_df = edited_df

    # Duplicate button — duplicate ต่อแถว, dropdown เลือกจาก "HAC Name - Side"
    if len(edited_df) > 0:
        dup_options = [f"{r['HAC Name']} - {r['Side']}" for _, r in edited_df.iterrows()]
        col1, col2 = st.columns([3, 1])
        with col1:
            dup_choice = st.selectbox("Duplicate HAC", options=dup_options, key="dup_select")
        with col2:
            st.write(""); st.write("")
            if st.button("➕ Duplicate", use_container_width=True):
                dup_idx = dup_options.index(dup_choice)
                row      = edited_df.iloc[dup_idx].copy()
                base     = row["HAC Name"]
                existing = set(edited_df["HAC Name"].tolist())
                new_name = base + " copy"
                c = 2
                while new_name in existing:
                    new_name = f"{base} copy{c}"; c += 1
                row["HAC Name"] = new_name
                row["Side"] = "บน"
                st.session_state.hac_df = pd.concat(
                    [st.session_state.hac_df, pd.DataFrame([row])], ignore_index=True
                )
                st.rerun()

    # Summary metrics — parse rack layout
    edited_df = edited_df.dropna(subset=["HAC Name"]).copy()
    edited_df["_rack_list"]  = edited_df["Rack Layout (kW)"].apply(parse_rack_layout)
    edited_df["_rack_count"] = edited_df["_rack_list"].apply(len)
    edited_df["_row_kw"]     = edited_df["_rack_list"].apply(sum)

    # validate — แสดง error ถ้า parse ไม่ได้
    invalid = edited_df[edited_df["_rack_count"] == 0]["HAC Name"].tolist()
    if invalid:
        st.warning(f"⚠️ กรอก Rack Layout ไม่ถูกต้องใน: {', '.join(invalid)} — ตัวอย่าง: 20, 150, 150, 20")

    total_all = edited_df.groupby("HAC Name")["_row_kw"].sum().sum()
    hac_first = edited_df.drop_duplicates(subset="HAC Name", keep="first")
    cnt_2src  = (hac_first["Source Type"] == "2-source").sum()
    cnt_4src  = (hac_first["Source Type"] == "4-source").sum()

    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("จำนวน HAC",          edited_df["HAC Name"].nunique())
    c2.metric("จำนวนแถวทั้งหมด",    len(edited_df))
    c3.metric("Total IT Load (kW)", f"{total_all:,.0f}")
    c4.metric("HAC แบบ 2-source",   cnt_2src)
    c5.metric("HAC แบบ 4-source",   cnt_4src)

    # ── แนะนำ Config อัตโนมัติ (คร่าวๆ ไม่ solve MILP — แค่เลขคณิตหารเท่าๆกัน+เทียบ Standard Size
    # เดียวกับ Equipment Sizing tab) ให้เห็นว่า n_groups/n_ups_per_group แบบไหนน่าลอง ก่อนต้อง
    # กด solve MILP จริงทีละแบบ ───────────────────────────────────────────────────
    st.divider()
    with st.expander("🎯 แนะนำ Config อัตโนมัติ (ประมาณคร่าวๆ ก่อน — ไม่ใช่คำตอบสุดท้าย)", expanded=False):
        st.caption(
            "หารโหลดรวมเท่าๆกันทุกกลุ่ม (ประมาณคร่าวๆ ของจริง MILP จะแบ่งไม่เท่ากันเป๊ะ) แล้วเทียบกับ "
            "Standard Size List เดียวกับแท็บ Equipment Sizing เพื่อดู utilization — ใช้เลือก 2-3 config "
            "ที่น่าสนใจมาลอง solve MILP จริงต่อ ไม่ใช่ตัดสินใจสุดท้ายจากตรงนี้"
        )
        if st.button("🔍 หา Config ที่แนะนำ"):
            sizing_cfg_fallback = st.session_state.get("sizing_cfg", {
                "ups_eff": 0.96, "ups_charging": 88.0, "tx_loss": 0.015, "hvac_total": 80.9,
                "pf": 0.95, "voltage": 415.0, "design_margin": 1.25, "util_threshold": 0.95,
                "ups_sizes": [500, 750, 1000, 1250, 1500, 1600, 2000, 2400, 2500],
                "trafo_sizes": [1000, 1250, 1600, 2000, 2200, 2500, 3000],
                "gen_sizes": [1250, 1500, 1750, 2000, 2200, 2500, 2750, 3000],
                "busway_sizes": [800, 1600, 2000, 2500, 3200, 4000, 5000],
            })
            st.session_state.suggested_configs = suggest_group_configs(total_all, sizing_cfg_fallback)

        suggestions = st.session_state.get("suggested_configs")
        if suggestions:
            if not st.session_state.get("sizing_cfg"):
                st.info("ℹ️ ยังไม่เคยเปิดแท็บ Equipment Sizing ในเซสชันนี้ — ใช้ค่า Assumption/Standard Size เริ่มต้นไปก่อน")
            for rank, r in enumerate(suggestions[:8], 1):
                cols = st.columns([1, 1, 1, 1, 1, 1, 1])
                badge = "🥇" if rank == 1 and r["feasible"] else ("❌" if not r["feasible"] else "")
                cols[0].markdown(f"**{badge} #{rank}**")
                cols[1].markdown(f"{r['n_groups']} กลุ่ม")
                cols[2].markdown(f"{r['n_ups_per_group']} PTU/กลุ่ม")
                if r["feasible"]:
                    cols[3].markdown(f"avg util **{r['avg_util']*100:.0f}%**")
                    eq = r["equip"]
                    cols[4].markdown(f"UPS {eq['ups']['size']:,.0f}kW")
                    cols[5].markdown(f"Gen {eq['gen']['size']:,.0f}kW")
                else:
                    cols[3].markdown("❌ ไม่มี size รองรับ")
                if cols[6].button("ใช้ config นี้", key=f"apply_suggest_{rank}"):
                    st.session_state["n_groups_input"] = r["n_groups"]
                    st.session_state["n_ups_per_group_select"] = r["n_ups_per_group"]
                    st.rerun()

    # Settings
    st.divider()
    st.subheader("⚙️ ตั้งค่า Optimization")
    n_groups = st.number_input(
        "จำนวนกลุ่ม PTU 1กลุ่ม อาจมี 4,5,6 PTU(ABCD..) (default = 3)",
        min_value=1, max_value=6, value=3, step=1, key="n_groups_input",
    )
    st.session_state.n_groups = int(n_groups)
    n_ups_per_group = st.selectbox(
        "จำนวน PTU/UPS ต่อกลุ่ม",
        options=N_UPS_PER_GROUP_OPTIONS, index=0, key="n_ups_per_group_select",
        format_func=lambda n: f"{n} PTU ({''.join(get_group_ups_units(n))})",
        help="ปกติกลุ่มนึงมี 4 PTU (A,B,C,D) — ถ้าเลือก 5/6 แถวที่เป็น 2-source จะจับคู่ (pair) ได้หลากหลาย"
             "ขึ้นตามจำนวนที่เลือก (4→6 แบบ, 5→10 แบบ, 6→15 แบบ) ส่วนแถว 4-source ยังเสียบแค่ 4 เส้นเท่าเดิม"
             "เพียงแต่ MILP จะเลือกด้วยว่าเสียบเข้า PTU ตัวไหนใน 5/6 ตัว",
    )
    st.session_state.n_ups_per_group = int(n_ups_per_group)
    time_limit = st.number_input(
        "Time Limit ต่อการ solve (วินาที)",
        min_value=5, max_value=1800, value=DEFAULT_TIME_LIMIT, step=5,
        help="ใช้ร่วมกันทั้งปุ่ม Contiguous และ Free — เวลาสูงสุดที่ solver รอก่อนคืนคำตอบที่ดีที่สุด ณ จุดนั้น",
    )
    st.session_state.time_limit = int(time_limit)

    # Diagram
    st.divider()
    st.subheader("แผนภาพ Data Hall")
    if len(edited_df) > 0:
        hac_list = [
            {
                "name": name,
                "rows": [
                    {
                        "side":        r["Side"],
                        "rack_list":   r["_rack_list"],
                        "source_type": r.get("Source Type", "2-source"),
                    }
                    for _, r in grp.iterrows()
                ],
            }
            for name, grp in edited_df.groupby("HAC Name", sort=False)
        ]
        st.markdown(build_hac_svg(hac_list), unsafe_allow_html=True)
        st.caption("ขอบสีม่วง = 4-source | ตัวเลขในแต่ละตู้คือ kW จริง | สีพื้นหลังแถวจะแสดงหลังคำนวณ")

    st.divider()
    col_run1, col_run2 = st.columns(2)
    with col_run1:
        if st.button("🔒 คำนวณ Pairing (Contiguous)", type="primary", use_container_width=True):
            st.session_state.run_optimization = True
            st.session_state.optimization_mode = "contiguous"
            st.success("✅ คำนวณเสร็จแล้ว — เปิดแท็บ ผลลัพธ์ เพื่อดูผล")
    with col_run2:
        if st.button("🔓 คำนวณ Pairing (ไม่จำกัดลำดับ)", use_container_width=True):
            st.session_state.run_optimization = True
            st.session_state.optimization_mode = "free"
            st.success("✅ คำนวณเสร็จแล้ว (โหมดไม่จำกัดลำดับ — ใช้เทียบเท่านั้น ห้ามเดินสายจริง) — เปิดแท็บ ผลลัพธ์ เพื่อดูผล")
    st.caption("🔓 โหมด 'ไม่จำกัดลำดับ' จับกลุ่มข้ามหัวกันได้อิสระ ไม่มีข้อจำกัดทางกายภาพ — ใช้เป็นเครื่องมือเทียบว่าดีกว่าปัจจุบันแค่ไหนเท่านั้น ห้ามเอาไปเดินสายจริง")




