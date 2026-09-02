"""
TAB 2: RESULTS — Pairing Optimization ผลลัพธ์
"""
import streamlit as st
import pandas as pd

from constants import UPS_UNITS, GROUP_BADGE_COLORS
from engine.pairing import (
    parse_rack_layout, build_row_units, brute_force_grouping,
    assign_pairing, compute_normal_loads, compute_fault_loads,
)
from ui.svg_diagram import build_hac_svg


def render():
    edited_df = st.session_state.hac_df.dropna(subset=["HAC Name"]).copy()
    if "Source Type" not in edited_df.columns:
        edited_df["Source Type"] = "2-source"
    edited_df["_rack_list"]    = edited_df["Rack Layout (kW)"].apply(parse_rack_layout)
    edited_df["_rack_count"]   = edited_df["_rack_list"].apply(len)
    edited_df["_row_kw"]       = edited_df["_rack_list"].apply(sum)
    edited_df["Total kW / HAC"] = edited_df["_row_kw"] * 2

    if len(edited_df) == 0:
        st.info("กรอกข้อมูล HAC ในแท็บก่อน")
        st.stop()
    if not st.session_state.get("run_optimization", False):
        st.info("กดปุ่ม **คำนวณ Pairing Optimization** ในแท็บกรอกข้อมูลก่อน")
        st.stop()

    n_groups = st.session_state.get("n_groups", 3)

    # ── ENGINE ───────────────────────────────────────────────────
    row_units   = build_row_units(edited_df)
    groups_raw, best_spread = brute_force_grouping(row_units, n_groups)
    groups      = assign_pairing(groups_raw)

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
    cols[-1].metric("ส่วนต่าง Max-Min (kW)", f"{best_spread:,.0f}")

    hac_list = [
        {
            "name":        r["HAC Name"],
            "count":       r["_rack_count"],
            "load":        r["_row_kw"] / r["_rack_count"] if r["_rack_count"] > 0 else 0,
            "rack_list":   r["_rack_list"],
            "source_type": r.get("Source Type", "2-source"),
        }
        for _, r in edited_df.iterrows()
    ]
    st.markdown(build_hac_svg(hac_list, groups), unsafe_allow_html=True)

    # ── SECTION 2: PAIRING TABLE ─────────────────────────────────
    st.header("2 — Pairing แต่ละแถว")
    for gi, grp in enumerate(groups, 1):
        color = GROUP_BADGE_COLORS[(gi - 1) % len(GROUP_BADGE_COLORS)]
        st.markdown(
            f'<div style="background:{color};padding:6px 14px;border-radius:6px;'
            f'font-weight:700;margin-bottom:6px">PTU Group {gi}</div>',
            unsafe_allow_html=True,
        )
        rows_out = []
        for row in grp:
            n = compute_normal_loads([row])
            src_label = row["source_type"]
            pair_label = "ABCD (25% each)" if row["source_type"] == "4-source" else row["pair"]
            rows_out.append({
                "HAC":         row["hac"],
                "แถว":         row["side"],
                "Source":      src_label,
                "kW":          f"{row['kw']:,.0f}",
                "Pairing":     pair_label,
                "→A":          f"{n['A']:,.0f}" if n["A"] else "—",
                "→B":          f"{n['B']:,.0f}" if n["B"] else "—",
                "→C":          f"{n['C']:,.0f}" if n["C"] else "—",
                "→D":          f"{n['D']:,.0f}" if n["D"] else "—",
            })
        st.dataframe(pd.DataFrame(rows_out), use_container_width=True, hide_index=True)

    # ── SECTION 3: NORMAL LOAD ───────────────────────────────────
    st.header("3 — Normal Operation Load ต่อ UPS ต่อกลุ่ม")
    norm_rows = []
    for gi, grp in enumerate(groups, 1):
        n = compute_normal_loads(grp)
        norm_rows.append({
            "กลุ่ม":      f"Group{gi}",
            "A (kW)":     f"{n['A']:,.0f}",
            "B (kW)":     f"{n['B']:,.0f}",
            "C (kW)":     f"{n['C']:,.0f}",
            "D (kW)":     f"{n['D']:,.0f}",
            "Total (kW)": f"{sum(n.values()):,.0f}",
        })
    st.dataframe(pd.DataFrame(norm_rows), use_container_width=True, hide_index=True)

    # ── SECTION 4: FAULT SIMULATION ──────────────────────────────
    st.header("4 — Failure Conditions")
    group_max_faults = []
    for gi, grp in enumerate(groups, 1):
        color = GROUP_BADGE_COLORS[(gi - 1) % len(GROUP_BADGE_COLORS)]
        st.markdown(
            f'<div style="background:{color};padding:6px 14px;border-radius:6px;'
            f'font-weight:700;margin-bottom:6px">PTU Group {gi}</div>',
            unsafe_allow_html=True,
        )
        fault_rows = []
        grp_max    = 0.0
        for faulted in UPS_UNITS:
            loads   = compute_fault_loads(grp, faulted)
            mx_ups  = max(loads, key=loads.get)
            mx_val  = loads[mx_ups]
            grp_max = max(grp_max, mx_val)
            row_out = {"UPS พัง ⚡": faulted}
            for u in UPS_UNITS:
                row_out[f"UPS {u} (kW)"] = "FAIL" if u == faulted else f"{loads[u]:,.0f}"
            row_out["Max Load"] = f"{mx_ups} = {mx_val:,.0f} kW"
            fault_rows.append(row_out)
        st.dataframe(pd.DataFrame(fault_rows), use_container_width=True, hide_index=True)
        group_max_faults.append({"กลุ่ม": f"Group{gi}", "Max Fault Load (kW)": grp_max})

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
