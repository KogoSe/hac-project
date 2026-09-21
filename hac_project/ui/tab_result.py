"""
TAB 2: RESULTS — Pairing Optimization ผลลัพธ์
"""
import streamlit as st
import pandas as pd

from constants import GROUP_BADGE_COLORS, ups_display_label, get_group_ups_units
from engine.pairing import (
    parse_rack_layout, build_row_units, compute_normal_loads, compute_fault_loads,
)
from engine.optimization import DEFAULT_TIME_LIMIT, solve_pairing_milp, solve_pairing_milp_free
from ui.svg_diagram import build_hac_svg

# ── สีสำหรับตาราง Load Breakdown — ไล่ตามตำแหน่ง UPS ในกลุ่ม (ไม่ผูกกับชื่อตัวอักษรตายตัวอีกแล้ว
# เพราะจำนวน UPS ต่อกลุ่มปรับได้ 4/5/6) วนซ้ำถ้า UPS มากกว่าจำนวนสีที่มี ──────────────────
SCENARIO_HEADER_COLORS = ["#DBEAFE", "#DCFCE7", "#FEF3C7", "#F3E8FF", "#FCE7F3", "#E0F2FE"]
SCENARIO_BORDER_COLORS = ["#3B82F6", "#22C55E", "#F59E0B", "#A855F7", "#EC4899", "#0EA5E9"]
NORMAL_HEADER_COLOR = "#F1F5F9"
NORMAL_BORDER_COLOR = "#94A3B8"
FAIL_BG = "#FEE2E2"
FAIL_TEXT = "#DC2626"
MAX_HIGHLIGHT_BG = "#FDE68A"


def build_load_breakdown_table(grp: list[dict], gi: int, ups_units: list, n_ups_per_group: int) -> str:
    """สร้าง HTML table แสดง load แต่ละแถวต่อ UPS ทุก scenario (Normal + Fault ทีละตัว)"""
    scenarios = ["Normal"] + ups_units  # key ภายใน (A,B,C,...) — ป้ายแสดงผลแปลงแยกด้านล่าง
    labels = {u: ups_display_label(gi, u, n_ups_per_group) for u in ups_units}
    border_color = {"Normal": NORMAL_BORDER_COLOR}
    header_color = {"Normal": NORMAL_HEADER_COLOR}
    for i, u in enumerate(ups_units):
        border_color[u] = SCENARIO_BORDER_COLORS[i % len(SCENARIO_BORDER_COLORS)]
        header_color[u] = SCENARIO_HEADER_COLORS[i % len(SCENARIO_HEADER_COLORS)]

    row_labels = []
    values = []  # list of {scenario: {unit: float|None|"FAIL"}}
    totals = {sc: {u: 0.0 for u in ups_units} for sc in scenarios}

    for row in grp:
        row_labels.append((row["hac"], row["side"], row["kw"]))
        row_vals = {}

        n = compute_normal_loads([row], ups_units)
        row_vals["Normal"] = {u: (n[u] if n[u] else None) for u in ups_units}
        for u in ups_units:
            totals["Normal"][u] += n[u]

        for faulted in ups_units:
            f = compute_fault_loads([row], faulted, ups_units)
            sc_vals = {}
            for u in ups_units:
                if u == faulted:
                    sc_vals[u] = "FAIL"
                else:
                    val = f.get(u, 0.0)
                    sc_vals[u] = val if val else None
                    totals[faulted][u] += val
            row_vals[faulted] = sc_vals
        values.append(row_vals)

    # หา max ต่อ scenario (จาก total) สำหรับไฮไลท์
    max_per_scenario = {
        sc: (max([v for v in totals[sc].values() if v], default=None))
        for sc in scenarios
    }

    n_units = len(ups_units)
    html = ['<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:13px;width:100%">']

    # Header แถว 1 — ชื่อ scenario
    html.append("<tr>")
    html.append('<th style="padding:6px 10px;background:#E2E8F0;border:1px solid #CBD5E1">HAC</th>')
    html.append('<th style="padding:6px 10px;background:#E2E8F0;border:1px solid #CBD5E1">แถว</th>')
    html.append('<th style="padding:6px 10px;background:#E2E8F0;border:1px solid #CBD5E1">kW</th>')
    for sc in scenarios:
        label = "Normal" if sc == "Normal" else f"{labels[sc]} Fail"
        border, bg = border_color[sc], header_color[sc]
        html.append(
            f'<th colspan="{n_units}" style="padding:6px 10px;background:{bg};'
            f'border:1px solid #CBD5E1;border-left:4px solid {border};text-align:center">{label}</th>'
        )
    html.append("</tr>")

    # Header แถว 2 — ตัวอักษร UPS แต่ละตัว
    html.append("<tr>")
    html.append('<th style="border:1px solid #CBD5E1;background:#F8FAFC"></th>' * 3)
    for sc in scenarios:
        border = border_color[sc]
        for i, u in enumerate(ups_units):
            lb = f"border-left:4px solid {border};" if i == 0 else ""
            html.append(f'<th style="padding:4px 8px;background:#F8FAFC;border:1px solid #CBD5E1;{lb}">{labels[u]}</th>')
    html.append("</tr>")

    # Data rows
    for (hac, side, kw), row_vals in zip(row_labels, values):
        html.append("<tr>")
        html.append(f'<td style="padding:5px 10px;border:1px solid #E2E8F0">{hac}</td>')
        html.append(f'<td style="padding:5px 10px;border:1px solid #E2E8F0">{side}</td>')
        html.append(f'<td style="padding:5px 10px;border:1px solid #E2E8F0;text-align:right">{kw:,.0f}</td>')
        for sc in scenarios:
            border = border_color[sc]
            for i, u in enumerate(ups_units):
                val = row_vals[sc][u]
                lb = f"border-left:4px solid {border};" if i == 0 else ""
                if val == "FAIL":
                    html.append(f'<td style="padding:5px 8px;border:1px solid #E2E8F0;{lb}background:{FAIL_BG};color:{FAIL_TEXT};font-weight:700;text-align:center">FAIL</td>')
                elif val is None:
                    html.append(f'<td style="padding:5px 8px;border:1px solid #E2E8F0;{lb}"></td>')
                else:
                    html.append(f'<td style="padding:5px 8px;border:1px solid #E2E8F0;{lb}text-align:right">{val:,.0f}</td>')
        html.append("</tr>")

    # Total row
    html.append('<tr style="background:#F1F5F9;font-weight:700">')
    html.append('<td colspan="3" style="padding:6px 10px;border:1px solid #CBD5E1">Total Power Consumption</td>')
    for sc in scenarios:
        border = border_color[sc]
        for i, u in enumerate(ups_units):
            lb = f"border-left:4px solid {border};" if i == 0 else ""
            total_val = totals[sc][u]
            is_max = max_per_scenario[sc] is not None and total_val == max_per_scenario[sc] and total_val > 0
            bg = f"background:{MAX_HIGHLIGHT_BG};" if is_max else ""
            display = f"{total_val:,.0f}" if total_val else ""
            html.append(f'<td style="padding:6px 8px;border:1px solid #CBD5E1;{lb}{bg}text-align:right">{display}</td>')
    html.append("</tr>")

    # Grand Total row ต่อ scenario — รวมจาก totals (float เต็ม ไม่ผ่านการปัดใดๆ) ไม่ใช่บวกเลขที่ปัดแล้ว
    # ในตารางย้อนกลับ เพื่อยืนยันว่าทุก scenario กระจายโหลดรวมเท่ากันจริง (เผื่อกรณีบวกเลขที่ปัดแล้วในตาราง
    # ด้วยมือแล้วผลรวมไม่ลงตัวเป๊ะ ซึ่งเป็นธรรมชาติของการปัดแยกแต่ละช่อง ไม่ใช่ค่าที่คำนวณผิด)
    html.append('<tr style="background:#E2E8F0;font-weight:700">')
    html.append('<td colspan="3" style="padding:6px 10px;border:1px solid #CBD5E1">รวมทั้งหมด (ยืนยันว่าเท่ากันทุก Scenario)</td>')
    for sc in scenarios:
        scenario_total = sum(totals[sc].values())
        html.append(
            f'<td colspan="{n_units}" style="padding:6px 10px;border:1px solid #CBD5E1;'
            f'text-align:center">{scenario_total:,.1f}</td>'
        )
    html.append("</tr>")

    html.append("</table></div>")
    return "".join(html)


def render():
    edited_df = st.session_state.hac_df.dropna(subset=["HAC Name"]).copy()
    if "Source Type" not in edited_df.columns:
        edited_df["Source Type"] = "2-source"
    edited_df["_rack_list"]    = edited_df["Rack Layout (kW)"].apply(parse_rack_layout)
    edited_df["_rack_count"]   = edited_df["_rack_list"].apply(len)
    edited_df["_row_kw"]       = edited_df["_rack_list"].apply(sum)

    if len(edited_df) == 0:
        st.info("กรอกข้อมูล HAC ในแท็บก่อน")
        st.stop()
    if not st.session_state.get("run_optimization", False):
        st.info("กดปุ่ม **คำนวณ Pairing Optimization** ในแท็บกรอกข้อมูลก่อน")
        st.stop()

    n_groups = st.session_state.get("n_groups", 3)
    n_ups_per_group = st.session_state.get("n_ups_per_group", 4)
    ups_units = get_group_ups_units(n_ups_per_group)
    time_limit = st.session_state.get("time_limit", DEFAULT_TIME_LIMIT)
    mode = st.session_state.get("optimization_mode", "contiguous")

    # ── ENGINE (MILP: grouping + pairing รวมเป็นโมเดลเดียว, minimize max-fail-load) ──
    try:
        row_units = build_row_units(edited_df)
    except ValueError as e:
        st.error(f"❌ ข้อมูล HAC ไม่ถูกต้อง: {e}")
        st.stop()

    # ── Cache ผล solve ด้วย input จริง — Streamlit rerun สคริปต์ทั้งหน้าทุกครั้งที่มี
    # interaction ที่ไหนก็ได้ในแอป (ทุกแท็บ render() ถูกเรียกใหม่หมดเสมอ ไม่ใช่แค่แท็บที่เปิดอยู่)
    # ถ้าไม่ cache ตรงนี้ การกดปุ่มใน tab อื่น (เช่น Generate Proof, แก้ค่าใน Equipment Sizing)
    # จะทำให้ solve MILP ใหม่ทั้งหมดทุกครั้งโดยไม่จำเป็น ทั้งที่ข้อมูล/การตั้งค่าไม่ได้เปลี่ยนเลย
    rows_key = tuple((r["hac"], r["side"], r["kw"], r["source_type"]) for r in row_units)
    warm_start_groups = st.session_state.get("last_contiguous_groups") if mode == "free" else None
    warm_key = (
        tuple(tuple((r["hac"], r["side"]) for r in grp) for grp in warm_start_groups)
        if warm_start_groups else None
    )
    solve_key = (rows_key, n_groups, n_ups_per_group, mode, time_limit, warm_key)

    if st.session_state.get("milp_cache_key") == solve_key and st.session_state.get("milp_result") is not None:
        milp_result = st.session_state.milp_result
    else:
        if mode == "free":
            milp_result = solve_pairing_milp_free(
                row_units, n_groups, n_ups_per_group=n_ups_per_group,
                time_limit=time_limit, warm_start_groups=warm_start_groups
            )
        else:
            milp_result = solve_pairing_milp(row_units, n_groups, n_ups_per_group=n_ups_per_group, time_limit=time_limit)
            st.session_state.last_contiguous_groups = milp_result["groups"]
        st.session_state.milp_result = milp_result  # ให้ tab_proof.py ใช้ต่อ (ไม่ solve ซ้ำ)
        st.session_state.milp_cache_key = solve_key
    groups = milp_result["groups"]

    if mode == "free":
        st.warning("🔓 **โหมดไม่จำกัดลำดับ** — ผลนี้ใช้เทียบเฉยๆ ว่าถ้าไม่มีข้อจำกัดทางกายภาพจะดีกว่าปัจจุบันแค่ไหน ห้ามเอาไปเดินสายจริง")

    # ── SECTION 1: GROUPING ──────────────────────────────────────
    st.header("1 — การแบ่งกลุ่ม PTU Groups")
    group_rows = []
    for gi, grp in enumerate(groups, 1):
        total_kw = sum(r["kw"] for r in grp)
        n4 = sum(1 for r in grp if r["source_type"] == "4-source")
        n2 = len(grp) - n4
        group_rows.append({
            "กลุ่ม":       f"G{gi}",
            "จาก":         f"{grp[0]['hac']} แถว{grp[0]['side']}",
            "ถึง":         f"{grp[-1]['hac']} แถว{grp[-1]['side']}",
            "แถวทั้งหมด":  len(grp),
            "2-source":    n2,
            "4-source":    n4,
            "Total kW":    f"{total_kw:,.0f}",
        })
    st.dataframe(pd.DataFrame(group_rows), use_container_width=True, hide_index=True)

    cols = st.columns(n_groups + 1)
    for gi, grp in enumerate(groups, 1):
        cols[gi - 1].metric(f"G{gi} Total kW", f"{sum(r['kw'] for r in grp):,.0f}")
    cols[-1].metric("Max-Fail-Load (MILP)", f"{milp_result['objective']:,.0f} kW", help="ดูรายละเอียด/proof ในแท็บ Optimization Proof")

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
    st.markdown(build_hac_svg(hac_list, groups, n_ups_per_group), unsafe_allow_html=True)

    # ── SECTION 2: PAIRING TABLE ─────────────────────────────────
    st.header("2 — Pairing แต่ละแถว")
    for gi, grp in enumerate(groups, 1):
        color = GROUP_BADGE_COLORS[(gi - 1) % len(GROUP_BADGE_COLORS)]
        st.markdown(
            f'<div style="background:{color};padding:6px 14px;border-radius:6px;'
            f'font-weight:700;margin-bottom:6px">PTU Group {gi}</div>',
            unsafe_allow_html=True,
        )
        labels = {u: ups_display_label(gi, u, n_ups_per_group) for u in ups_units}
        rows_out = []
        for row in grp:
            n = compute_normal_loads([row], ups_units)
            src_label = row["source_type"]
            pair_label = "".join(labels[ch] for ch in row["pair"])
            if row["source_type"] == "4-source":
                pair_label += f" ({100 / len(row['pair']):.0f}% each)"
            row_out = {
                "HAC":     row["hac"],
                "แถว":     row["side"],
                "Source":  src_label,
                "kW":      f"{row['kw']:,.0f}",
                "Pairing": pair_label,
            }
            for u in ups_units:
                row_out[f"→{labels[u]}"] = f"{n[u]:,.0f}" if n[u] else "—"
            rows_out.append(row_out)
        st.dataframe(pd.DataFrame(rows_out), use_container_width=True, hide_index=True)

    # ── SECTION 3: NORMAL LOAD ───────────────────────────────────
    # ต่อกลุ่มมี UPS เป็นชุดตัวอักษรของตัวเอง (กลุ่ม 1 = ABCD, กลุ่ม 2 = EFGH, ...) เลยแยกตาราง
    # รายกลุ่มแทนตารางรวม เพราะชื่อคอลัมน์ A/B/C/D ไม่ตรงกันข้ามกลุ่มแล้ว
    st.header("3 — Normal Operation Load ต่อ UPS ต่อกลุ่ม")
    for gi, grp in enumerate(groups, 1):
        n = compute_normal_loads(grp, ups_units)
        labels = {u: ups_display_label(gi, u, n_ups_per_group) for u in ups_units}
        norm_row = {"กลุ่ม": f"Group{gi}"}
        for u in ups_units:
            norm_row[f"{labels[u]} (kW)"] = f"{n[u]:,.0f}"
        norm_row["Total (kW)"] = f"{sum(n.values()):,.0f}"
        st.dataframe(pd.DataFrame([norm_row]), use_container_width=True, hide_index=True)

    # ── SECTION 4: FAILURE CONDITIONS — Load Breakdown ───────────
    st.header("4 — Failure Conditions")
    st.caption("🔴 แดง = UPS ที่ fail | เส้นสี = แบ่งกลุ่ม scenario | 🟡 เหลือง = จุดโหลดสูงสุดในแต่ละ scenario")

    group_max_faults = []
    for gi, grp in enumerate(groups, 1):
        # คำนวณ max fault load ของกลุ่ม (ใช้ต่อใน Section 5)
        grp_max = 0.0
        for faulted in ups_units:
            loads = compute_fault_loads(grp, faulted, ups_units)
            grp_max = max(grp_max, max(loads.values()))
        group_max_faults.append({"กลุ่ม": f"Group{gi}", "Max Fault Load (kW)": grp_max})

        with st.expander(f"📋 PTU Group {gi} — Load Breakdown", expanded=False):
            st.markdown(build_load_breakdown_table(grp, gi, ups_units, n_ups_per_group), unsafe_allow_html=True)

    # ── SECTION 5: SUMMARY ───────────────────────────────────────
    st.header("5 — สรุป Max Load When Fault Condition ทุกกลุ่ม")
    st.caption("ใช้เป็นฐานคำนวณขนาด Generator / Transformer / Busbar")

    summary_df  = pd.DataFrame(group_max_faults)
    overall_max = summary_df["Max Fault Load (kW)"].max()

    cols = st.columns(n_groups + 1)
    for gi, row in enumerate(group_max_faults, 1):
        cols[gi - 1].metric(f"Group{gi} Max Fault", f"{row['Max Fault Load (kW)']:,.0f} kW")
    cols[-1].metric("⚠️ Overall Max", f"{overall_max:,.0f} kW", delta="ใช้ sizing อุปกรณ์")

    st.dataframe(summary_df, use_container_width=True, hide_index=True)
