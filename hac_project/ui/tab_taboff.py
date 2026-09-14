"""
TAB: TAP-OFF — เลือกขนาด Breaker (ต่อ rack) และ Busway ย่อย (ต่อแถว HAC)
"""
import streamlit as st
import pandas as pd

from engine.pairing import parse_rack_layout
from engine.sizing import select_taboff_breaker, select_row_busway


def parse_sizes(s):
    try:
        return sorted([float(x.strip()) for x in s.split(",") if x.strip()])
    except Exception:
        return []


def render():
    st.header("🔌 Tap-off Sizing")
    st.caption("เลือกขนาด Breaker ของ Tap-off ต่อ rack และ Busway ย่อยเหนือแต่ละแถว HAC")

    sizing_cfg = st.session_state.get("sizing_cfg")
    if sizing_cfg is None:
        st.info("ไปที่แท็บ **Equipment Sizing** ก่อนอย่างน้อย 1 ครั้ง เพื่อตั้งค่า Voltage")
        st.stop()
    voltage = sizing_cfg["voltage"]

    hac_df = st.session_state.get("hac_df")
    if hac_df is None or len(hac_df) == 0:
        st.info("ไปที่แท็บ **กรอกข้อมูล** ก่อน เพื่อกรอก Rack Layout")
        st.stop()

    # ── Assumptions เฉพาะ tab นี้ ─────────────────────────
    with st.expander("⚙️ แก้ไข Assumption & Standard Sizes", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            rack_pf = st.number_input("Power Factor ของ Rack", value=0.95, step=0.01, key="taboff_rack_pf")
        with col2:
            margin = st.number_input("Design Margin", value=1.25, step=0.05, key="taboff_margin")
        st.caption(f"Voltage: {voltage:.0f} V (ค่าเดียวกับแท็บ Equipment Sizing — แก้ที่นั่นจุดเดียว)")

        st.divider()
        st.markdown("**Standard Size Lists** (แก้ไขได้ — คั่นด้วยจุลภาค)")
        sc1, sc2 = st.columns(2)
        with sc1:
            breaker_sizes_str = st.text_input(
                "Tap-off Breaker / MCCB (A)",
                value="16,20,25,32,40,50,63,80,100,125,160,200,225,250,300,350,400,500,630",
            )
        with sc2:
            row_busway_sizes_str = st.text_input(
                "Row Busway (A)",
                value="100,125,160,200,250,315,400,500,630,800,1000,1250,1600,2000,2500,3200,4000,5000",
            )

    breaker_sizes    = parse_sizes(breaker_sizes_str)
    row_busway_sizes = parse_sizes(row_busway_sizes_str)

    # ── หาค่า kW ที่ไม่ซ้ำกันทั้ง datahall (ทั้ง rack เดี่ยว และผลรวมต่อแถว) ──
    df = hac_df.dropna(subset=["HAC Name"]).copy()
    df["_rack_list"]  = df["Rack Layout (kW)"].apply(parse_rack_layout)
    df["_row_total"]  = df["_rack_list"].apply(sum)

    unique_rack_kw = sorted({kw for lst in df["_rack_list"] for kw in lst})
    unique_row_kw  = sorted(df["_row_total"].unique().tolist())

    if not unique_rack_kw:
        st.warning("⚠️ ไม่พบข้อมูล Rack Layout ที่ถูกต้อง — กรอกข้อมูลในแท็บ กรอกข้อมูล ก่อน")
        st.stop()

    # ── ส่วนที่ 1: Breaker ต่อ rack (คำนวณเฉพาะ kW ที่ไม่ซ้ำ) ──
    st.subheader("1️⃣ Tap-off Breaker ต่อ Rack")
    breaker_results = {
        kw: select_taboff_breaker(kw, rack_pf, voltage, margin, breaker_sizes)
        for kw in unique_rack_kw
    }
    st.dataframe(pd.DataFrame([
        {
            "Rack (kW)":   f"{kw:,.0f}",
            "Actual (A)":  f"{r['i_actual']:.1f}",
            "Design (A)":  f"{r['i_design']:.1f}",
            "Breaker (A)": f"{r['size']:,.0f}" if r["size"] else "❌ N/A",
            "Util %":      f"{r['util']*100:.1f}%" if r["util"] else "—",
        }
        for kw, r in breaker_results.items()
    ]), use_container_width=True, hide_index=True)

    st.divider()

    # ── ส่วนที่ 2: Busway ต่อแถว HAC (คำนวณเฉพาะผลรวมที่ไม่ซ้ำ) ──
    st.subheader("2️⃣ Busway เหนือแต่ละแถว HAC")
    busway_results = {
        kw: select_row_busway(kw, rack_pf, voltage, margin, row_busway_sizes)
        for kw in unique_row_kw
    }
    st.dataframe(pd.DataFrame([
        {
            "Row Total (kW)": f"{kw:,.0f}",
            "Actual (A)":     f"{r['i_actual']:.1f}",
            "Design (A)":     f"{r['i_design']:.1f}",
            "Busway (A)":     f"{r['size']:,.0f}" if r["size"] else "❌ N/A",
            "Util %":         f"{r['util']*100:.1f}%" if r["util"] else "—",
        }
        for kw, r in busway_results.items()
    ]), use_container_width=True, hide_index=True)

    # ── อ้างอิง: HAC ไหนใช้ busway ขนาดไหน ──
    st.markdown("**อ้างอิง: แต่ละ HAC ใช้ Busway ขนาดไหน**")
    st.dataframe(pd.DataFrame([
        {
            "HAC Name":       row["HAC Name"],
            "Row Total (kW)": f"{row['_row_total']:,.0f}",
            "Busway (A)":     f"{busway_results[row['_row_total']]['size']:,.0f}"
                               if busway_results[row['_row_total']]['size'] else "❌ N/A",
        }
        for _, row in df.iterrows()
    ]), use_container_width=True, hide_index=True)