"""
TAB — Optimization Proof: แสดงหลักฐานว่าผลลัพธ์ MILP น่าเชื่อถือ
- max-fail-load ที่ได้ (M*) + solver status (Optimal proven / time-limited + gap)
- lower bound เชิงทฤษฎี (group total / 3) และ lower bound จริงจาก solver (แน่นกว่า)
- brute-force cross-check: ตรึง grouping ที่ MILP หาได้ แล้ววนหา pairing ที่ดีที่สุดจริง
  (6^k) สำหรับกลุ่มที่มี 2-source <= 8 แถว เพื่อยืนยันว่ากลุ่มที่เป็น "คอขวด" (bottleneck —
  กลุ่มที่ max-fail-load เท่ากับ M* ของทั้งระบบ) MILP หา pairing ที่ optimal จริง
  ส่วนกลุ่มอื่นที่ไม่ใช่คอขวด ไม่จำเป็นต้อง optimal เป็นรายกลุ่ม (แค่ไม่เกิน M* ก็พอ)
"""
import streamlit as st
import pandas as pd

from constants import GROUP_BADGE_COLORS
from engine.optimization import evaluate_group_max_fail, brute_force_pairing_check

BOTTLENECK_TOL = 1e-6


def render():
    if not st.session_state.get("run_optimization", False):
        st.info("กดปุ่ม **คำนวณ Pairing Optimization** ในแท็บกรอกข้อมูลก่อน")
        st.stop()

    milp_result = st.session_state.get("milp_result")
    if milp_result is None:
        st.info("ยังไม่มีผลลัพธ์ MILP — ไปที่แท็บ **ผลลัพธ์** ก่อนเพื่อรัน optimization")
        st.stop()

    groups = milp_result["groups"]
    n_groups = len(groups)

    # ── SECTION 1: SOLVER STATUS ──────────────────────────────────
    st.header("1 — สถานะ Solver")
    c1, c2, c3 = st.columns(3)
    c1.metric("Solver Status", milp_result["status"])
    c2.metric("Max-Fail-Load (M*)", f"{milp_result['objective']:,.1f} kW")
    gap = milp_result.get("gap")
    c3.metric("Optimality Gap", f"{gap * 100:.2f}%" if gap is not None else "0% (proven)")

    if "proven" in milp_result["status"].lower():
        st.success("Solver พิสูจน์แล้วว่านี่คือคำตอบที่ดีที่สุดจริง (global optimum)")
    else:
        st.warning(
            "Solver หยุดเพราะครบเวลาที่กำหนด (time limit) — คำตอบที่ได้อาจไม่ใช่ optimum แท้จริง "
            "100% แต่รับประกันว่าอยู่ในช่วง gap ที่แสดงจาก lower bound จริง (ดู section 2)"
        )

    # ── SECTION 2: LOWER BOUNDS ────────────────────────────────────
    st.header("2 — Lower Bound (พิสูจน์ว่าลดต่อไปไม่ได้แค่ไหน)")
    lb1, lb2, lb3 = st.columns(3)
    lb1.metric(
        "Solver Lower Bound",
        f"{milp_result['solver_lower_bound']:,.1f} kW" if milp_result.get("solver_lower_bound") is not None else "—",
        help="Lower bound จริงจาก LP relaxation + cuts ของ CBC — แน่นกว่า theoretical bound",
    )
    lb2.metric(
        "Theoretical LB (กลุ่มที่ได้)",
        f"{milp_result['theoretical_lower_bound']:,.1f} kW",
        help="max(group total kW)/3 ของกลุ่มที่ solve ได้จริง — ถ้าแบ่งโหลด 3 UPS ที่เหลือได้เท่ากันเป๊ะ",
    )
    lb3.metric(
        "Global Theoretical LB",
        f"{milp_result['global_theoretical_lower_bound']:,.1f} kW",
        help="(total kW ทั้งหมด / จำนวนกลุ่ม) / 3 — floor ทางทฤษฎีที่เป็นไปได้ ไม่ขึ้นกับวิธีแบ่งกลุ่มจริง",
    )
    st.caption(
        "M* ต้อง >= ทุก lower bound ข้างบนเสมอ ถ้า M* ใกล้ Solver Lower Bound มาก แปลว่าคำตอบดีมากแล้ว"
    )

    # ── SECTION 3: BRUTE-FORCE CROSS-CHECK ────────────────────────
    st.header("3 — Brute-Force Cross-Check ต่อกลุ่ม")
    st.caption(
        "ตรึง grouping ตามที่ MILP หาได้ แล้ววนหา pairing ที่ดีที่สุดจริงทุกความเป็นไปได้ (6^k) "
        "เฉพาะกลุ่มที่มีแถว 2-source <= 8 แถว (k ใหญ่กว่านี้ 6^k จะช้าเกินไป) "
        "กลุ่มที่เป็น **คอขวด** (max-fail-load ของกลุ่ม = M* ของทั้งระบบ) ต้อง match กับ MILP เป๊ะ "
        "ส่วนกลุ่มอื่นไม่จำเป็นต้อง optimal รายกลุ่ม (แค่ไม่เกิน M* ก็พอแล้ว)"
    )

    overall_max = milp_result["objective"]
    check_rows = []
    for gi, grp in enumerate(groups, 1):
        group_max = evaluate_group_max_fail(grp)
        is_bottleneck = abs(group_max - overall_max) < BOTTLENECK_TOL
        n_two = sum(1 for r in grp if r["source_type"] != "4-source")

        color = GROUP_BADGE_COLORS[(gi - 1) % len(GROUP_BADGE_COLORS)]
        label = f"PTU Group {gi}" + ("  🎯 คอขวด (bottleneck)" if is_bottleneck else "")
        st.markdown(
            f'<div style="background:{color};padding:6px 14px;border-radius:6px;'
            f'font-weight:700;margin-bottom:6px">{label}</div>',
            unsafe_allow_html=True,
        )

        chk = brute_force_pairing_check(grp)
        if chk is None:
            st.info(f"กลุ่มนี้มี 2-source {n_two} แถว (> 8) — ข้ามการเช็ค brute-force (6^{n_two} ช้าเกินไป)")
            check_rows.append({
                "กลุ่ม": f"G{gi}", "คอขวด": "✅" if is_bottleneck else "—",
                "2-source rows": n_two, "MILP max-fail": f"{group_max:,.1f}",
                "Brute-force best": "ข้าม (>8 แถว)", "ยืนยันหรือไม่": "—",
            })
            continue

        if is_bottleneck:
            if chk["matches"]:
                st.success(
                    f"ยืนยันแล้ว: brute-force ({chk['combinations_tried']:,} combos) "
                    f"หา pairing ที่ดีที่สุดได้ {chk['brute_force_best']:,.1f} kW "
                    f"ตรงกับ MILP เป๊ะ → M* = {group_max:,.1f} kW ไม่สามารถลดต่อได้อีกจากกลุ่มนี้"
                )
            else:
                st.error(
                    f"⚠️ ไม่ตรงกัน! brute-force หาได้ {chk['brute_force_best']:,.1f} kW "
                    f"แต่ MILP ได้ {chk['milp_result']:,.1f} kW — ควรตรวจสอบโมเดล MILP"
                )
        else:
            st.caption(
                f"ไม่ใช่คอขวด (< M* = {overall_max:,.1f}) — brute-force best ของกลุ่มนี้คือ "
                f"{chk['brute_force_best']:,.1f} kW (MILP ไม่จำเป็นต้อง optimal รายกลุ่มนี้)"
            )

        check_rows.append({
            "กลุ่ม": f"G{gi}", "คอขวด": "🎯" if is_bottleneck else "—",
            "2-source rows": n_two, "MILP max-fail": f"{group_max:,.1f}",
            "Brute-force best": f"{chk['brute_force_best']:,.1f}",
            "ยืนยันหรือไม่": "✅ ตรงกัน" if (not is_bottleneck or chk["matches"]) else "❌ ไม่ตรง",
        })

    st.dataframe(pd.DataFrame(check_rows), use_container_width=True, hide_index=True)
