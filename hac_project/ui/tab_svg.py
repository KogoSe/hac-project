"""
TAB 7: SVG SIZING — Static Var Generator / Active Harmonic Filter sizing
ยืนคนละ flow จาก tab อื่นทั้งหมด ไม่พึ่ง session_state จาก tab_sizing
"""
import streamlit as st

from constants import SVG_STANDARD_SIZES
from engine.harmonic import size_svg


def render():
    st.header("SVG (Active Harmonic Filter) Sizing")
    st.caption(
        "ประมาณการช่วง design phase อ้างอิงตาราง IEEE-519-2014 (TDD limit ตาม Isc/IL) "
        "— ไม่ต้องมีข้อมูลวัดจริงจากไซต์"
    )

    col1, col2 = st.columns(2)
    with col1:
        il = st.number_input(
            "IL — Load current ที่ PCC (A)",
            min_value=0.0, value=100.0, step=1.0,
            help="กระแสโหลดสูงสุด (fundamental) ที่จุดจะติดตั้ง SVG",
        )
        isc = st.number_input(
            "Isc — Short-circuit current ที่ PCC (A)",
            min_value=0.0, value=2000.0, step=10.0,
            help="กระแสลัดวงจรสูงสุดที่จุดเดียวกัน",
        )
    with col2:
        thdi_load = st.number_input(
            "THDi ของโหลดก่อนติด filter (%)",
            min_value=0.0, max_value=100.0, value=30.0, step=1.0,
        )
        margin_percent = st.number_input(
            "Design margin (%)",
            min_value=0.0, max_value=100.0, value=20.0, step=5.0,
            help="เผื่อเหนือกระแสฮาร์มอนิกที่คำนวณได้ก่อนเลือกขนาดมาตรฐาน (default 20%)",
        )

    use_custom_target = st.checkbox(
        "กำหนด target THDi เอง (ค่าเริ่มต้น: ใช้ IEEE-519 TDD limit ตาม Isc/IL)"
    )
    tdd_target_percent = None
    if use_custom_target:
        tdd_target_percent = st.number_input(
            "Target THDi หลังติด filter (%)",
            min_value=0.0, max_value=100.0, value=8.0, step=1.0,
        )

    if st.button("คำนวณขนาด SVG", type="primary"):
        try:
            result = size_svg(
                il=il,
                isc=isc,
                thdi_load_percent=thdi_load,
                standard_sizes=SVG_STANDARD_SIZES,
                tdd_target_percent=tdd_target_percent,
                margin_percent=margin_percent,
            )
        except ValueError as e:
            st.error(str(e))
            return

        st.subheader("ผลลัพธ์")
        c1, c2, c3 = st.columns(3)
        c1.metric("Isc/IL ratio", f"{result.isc_il_ratio:.1f}")
        c2.metric("IEEE-519 TDD limit", f"{result.tdd_limit_percent:.1f}%")
        used_target = tdd_target_percent if tdd_target_percent is not None else result.tdd_limit_percent
        c3.metric("Target THDi ที่ใช้", f"{used_target:.1f}%")

        c4, c5, c6 = st.columns(3)
        c4.metric("Harmonic current ก่อน filter", f"{result.i_harmonic_before:.1f} A")
        c5.metric("Required filter current (raw)", f"{result.i_filter_required_raw:.1f} A")
        c6.metric(
            f"Required + margin {result.margin_percent:.0f}%",
            f"{result.i_filter_required_with_margin:.1f} A",
        )

        if result.selected_svg_size is not None:
            st.success(f"ขนาด SVG มาตรฐานที่เลือก: **{result.selected_svg_size} A**")
        else:
            st.warning("ไม่มีขนาดมาตรฐานเดี่ยวรองรับพอ — พิจารณาต่อขนานหลายโมดูล")

        if result.warning:
            st.warning(result.warning)
