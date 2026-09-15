"""
TAB — Optimization Proof: แสดงหลักฐานว่าผลลัพธ์ MILP น่าเชื่อถือ
- max-fail-load ที่ได้ (M*) + solver status (Optimal proven / time-limited + gap)
- lower bound เชิงทฤษฎี (group total / 3) และ lower bound จริงจาก solver (แน่นกว่า)
- brute-force cross-check: ตรึง grouping ที่ MILP หาได้ แล้ววนหา pairing ที่ดีที่สุดจริง
  (6^k) สำหรับกลุ่มที่มี 2-source <= 8 แถว เพื่อยืนยันว่ากลุ่มที่เป็น "คอขวด" (bottleneck —
  กลุ่มที่ max-fail-load เท่ากับ M* ของทั้งระบบ) MILP หา pairing ที่ optimal จริง
  ส่วนกลุ่มอื่นที่ไม่ใช่คอขวด ไม่จำเป็นต้อง optimal เป็นรายกลุ่ม (แค่ไม่เกิน M* ก็พอ)
- ปุ่ม generate .docx: ใช้ build_proof_context() ตัวเดียวกับที่ section 3 ใช้แสดงผล
  (ไม่คำนวณ evaluate_group_max_fail/brute_force_pairing_check ซ้ำสองที่)
"""
import streamlit as st
import pandas as pd

from constants import GROUP_BADGE_COLORS
from engine.optimization import build_proof_context
from engine.report_docx import build_optimization_proof_docx


def render():
    milp_result = st.session_state.get("milp_result") if st.session_state.get("run_optimization", False) else None
    proof_context = build_proof_context(milp_result) if milp_result is not None else None
    current_mode = milp_result.get("mode") if milp_result is not None else None

    col_doc1, col_doc2 = st.columns(2)
    with col_doc1:
        contiguous_context = proof_context if current_mode == "contiguous" else None
        st.download_button(
            label="📄 Generate Proof Document — Contiguous (.docx)",
            data=build_optimization_proof_docx(contiguous_context, mode="contiguous"),
            file_name="HAC_Optimization_Proof_Contiguous.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            help="เอกสารอธิบายหลักการโมเดล Contiguous (ใช้เดินสายจริงได้) ตั้งแต่ต้นจนจบ — "
                 "ส่วนหลักการคงที่เสมอ ส่วน Appendix B (ผลลัพธ์ของเคสนี้) จะแนบก็ต่อเมื่อผลล่าสุด "
                 "ใน session เป็นโหมด Contiguous เท่านั้น",
        )
    with col_doc2:
        free_context = proof_context if current_mode == "free" else None
        st.download_button(
            label="📄 Generate Proof Document — Free (.docx)",
            data=build_optimization_proof_docx(free_context, mode="free"),
            file_name="HAC_Optimization_Proof_Free.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            help="เอกสารอธิบายหลักการโมเดล Free/ไม่จำกัดลำดับ (สำหรับเทียบเท่านั้น ห้ามเดินสายจริง) — "
                 "ส่วนหลักการคงที่เสมอ ส่วน Appendix B (ผลลัพธ์ของเคสนี้) จะแนบก็ต่อเมื่อผลล่าสุด "
                 "ใน session เป็นโหมด Free เท่านั้น",
        )
    if current_mode is not None:
        st.caption(
            f"ผลลัพธ์ล่าสุดใน session นี้คือโหมด **{current_mode}** — เอกสารของอีกโหมดจะมีแค่ส่วนหลักการ "
            "ไม่มี Appendix B (ผลตัวเลขของเคสนี้) แนบมา เพราะยังไม่ได้รันโหมดนั้นล่าสุด"
        )
    st.divider()

    if not st.session_state.get("run_optimization", False):
        st.info("กดปุ่ม **คำนวณ Pairing Optimization** ในแท็บกรอกข้อมูลก่อน")
        st.stop()

    if milp_result is None:
        st.info("ยังไม่มีผลลัพธ์ MILP — ไปที่แท็บ **ผลลัพธ์** ก่อนเพื่อรัน optimization")
        st.stop()

    groups = milp_result["groups"]
    n_groups = len(groups)

    mode = milp_result.get("mode")
    if mode == "free":
        st.caption("🔓 Free (ไม่จำกัดลำดับ — สำหรับเทียบเท่านั้น ห้ามใช้เดินสายจริง)")
    elif mode == "contiguous":
        st.caption("🔒 Contiguous")

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
        "ส่วนกลุ่มอื่นไม่จำเป็นต้อง optimal เป็นรายกลุ่ม (แค่ไม่เกิน M* ก็พอแล้ว)"
    )

    overall_max = proof_context["overall_max"]
    check_rows = []
    for gc in proof_context["group_checks"]:
        gi, grp = gc["index"], gc["group"]
        group_max, is_bottleneck, n_two, chk = gc["group_max"], gc["is_bottleneck"], gc["n_two_source"], gc["brute_force"]

        color = GROUP_BADGE_COLORS[(gi - 1) % len(GROUP_BADGE_COLORS)]
        label = f"PTU Group {gi}" + ("  🎯 คอขวด (bottleneck)" if is_bottleneck else "")
        st.markdown(
            f'<div style="background:{color};padding:6px 14px;border-radius:6px;'
            f'font-weight:700;margin-bottom:6px">{label}</div>',
            unsafe_allow_html=True,
        )

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
