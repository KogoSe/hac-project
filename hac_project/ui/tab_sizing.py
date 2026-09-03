"""
TAB 3: EQUIPMENT SIZING — เลือกขนาด UPS / Transformer / Generator / Busway
"""
import streamlit as st
import pandas as pd

from constants import UPS_UNITS, GROUP_BADGE_COLORS
from engine.pairing import (
    parse_rack_layout, build_row_units, brute_force_grouping,
    assign_pairing, compute_normal_loads, compute_fault_loads,
)
from engine.sizing import compute_load_chain, select_equipment, unify_common_sizes, select_it_and_preups_busbar


def util_bar_html(util: float | None, threshold: float) -> str:
    """สร้าง HTML progress bar แสดง Utilization"""
    if util is None:
        return '<span style="color:#C00000;font-weight:700">❌ ไม่มี size รองรับ</span>'
    pct = util * 100
    color = "#16A34A" if pct < 80 else "#D97706" if pct <= threshold * 100 else "#DC2626"
    status = "✅ OK" if pct <= threshold * 100 else "❌ RISK"
    bar = f"""
    <div style="display:flex;align-items:center;gap:8px">
      <div style="flex:1;background:#E5E7EB;border-radius:4px;height:16px;overflow:hidden">
        <div style="width:{min(pct,100):.1f}%;background:{color};height:100%;border-radius:4px"></div>
      </div>
      <span style="font-size:12px;font-weight:600;color:{color};min-width:60px">{pct:.1f}% {status}</span>
    </div>"""
    return bar


def parse_sizes(s):
    try:
        return sorted([float(x.strip()) for x in s.split(",") if x.strip()])
    except Exception:
        return []


def render():
    st.header("⚙️ Equipment Sizing")

    # ── ตรวจสอบว่าคำนวณ Pairing แล้ว ──────────────────────────
    if not st.session_state.get("run_optimization", False):
        st.info("กดปุ่ม **คำนวณ Pairing Optimization** ในแท็บกรอกข้อมูลก่อน")
        st.stop()

    # ── SECTION: ASSUMPTIONS INPUT ──────────────────────────────
    st.subheader("ค่า Assumption")
    with st.expander("⚙️ แก้ไข Assumption & Standard Sizes", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            ups_eff      = st.number_input("UPS Efficiency (%)", value=96.0, step=0.5) / 100
            ups_charging = st.number_input("UPS Battery Charging (kW)", value=88.0, step=1.0)
        with col2:
            tx_loss      = st.number_input("Transmission Loss (%)", value=1.5, step=0.1) / 100
            hvac_total   = st.number_input("HVAC Load in PTU (kW)", value=80.9, step=1.0)
        with col3:
            pf           = st.number_input("Power Factor", value=0.95, step=0.01)
            voltage      = st.number_input("Voltage (V, 3-phase)", value=415.0, step=1.0)
        with col4:
            design_margin = st.number_input("Design Margin", value=1.25, step=0.05)
            util_threshold = st.number_input("Max Utilization (%)", value=95.0, step=1.0) / 100

        st.divider()
        st.markdown("**Standard Size Lists** (แก้ไขได้ — คั่นด้วยจุลภาค)")
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            ups_sizes_str = st.text_input("UPS (kW)", value="500,750,1000,1250,1500,1600,2000,2400,2500")
        with sc2:
            trafo_sizes_str = st.text_input("Transformer (kVA)", value="1000,1250,1600,2000,2500,3000,3150,4000")
        with sc3:
            gen_sizes_str = st.text_input("Generator (kW)", value="1250,1500,1750,2000,2200,2500,2750,3000,3500")
        with sc4:
            busway_sizes_str = st.text_input("Busway (A)", value="800,1600,2000,2500,3200,4000,5000")

    cfg = {
        "ups_eff":       ups_eff,
        "ups_charging":  ups_charging,
        "tx_loss":       tx_loss,
        "hvac_total":    hvac_total,
        "pf":            pf,
        "voltage":       voltage,
        "design_margin": design_margin,
        "util_threshold": util_threshold,
        "ups_sizes":     parse_sizes(ups_sizes_str),
        "trafo_sizes":   parse_sizes(trafo_sizes_str),
        "gen_sizes":     parse_sizes(gen_sizes_str),
        "busway_sizes":  parse_sizes(busway_sizes_str),
    }
    # เก็บไว้ให้ tab อื่น (เช่น tab 4 SLD) เรียกใช้ค่า assumption ล่าสุดได้
    st.session_state.sizing_cfg = cfg

    # ── rebuild groups จาก session state (ไม่แตะโค้ดเดิม) ──────
    edited_df_sz = st.session_state.hac_df.dropna(subset=["HAC Name"]).copy()
    if "Source Type" not in edited_df_sz.columns:
        edited_df_sz["Source Type"] = "2-source"
    edited_df_sz["_rack_list"] = edited_df_sz["Rack Layout (kW)"].apply(parse_rack_layout)
    edited_df_sz["_row_kw"]    = edited_df_sz["_rack_list"].apply(sum)
    n_groups_sz  = st.session_state.get("n_groups", 3)
    row_units_sz = build_row_units(edited_df_sz)
    groups_raw_sz, _ = brute_force_grouping(row_units_sz, n_groups_sz)
    groups_sz    = assign_pairing(groups_raw_sz)

    # ── PASS 1: คำนวณ chain + equipment ของทุกกลุ่มก่อน ─────────
    st.divider()
    summary_rows = []  # สำหรับ Comparison Summary
    group_calcs  = []  # เก็บผลของแต่ละกลุ่มไว้ก่อน render

    for gi, grp in enumerate(groups_sz, 1):
        grp_max_fault = 0.0
        for faulted in UPS_UNITS:
            loads = compute_fault_loads(grp, faulted)
            grp_max_fault = max(grp_max_fault, max(loads.values()))
        norm_loads = compute_normal_loads(grp)
        grp_normal_total = max(norm_loads.values())

        chain = compute_load_chain(grp_max_fault, grp_normal_total, cfg)
        equip = select_equipment(chain, cfg)
        equip.update(select_it_and_preups_busbar(chain, cfg))   # ← เพิ่มบรรทัดนี้
        group_calcs.append({"gi": gi, "chain": chain, "equip": equip})

    # ── หาขนาดใหญ่สุดของ UPS / Generator / Transformer / Busway ร่วมกันทุกกลุ่ม ──
        common_sizes = unify_common_sizes(
        [gc["equip"] for gc in group_calcs],
        keys=("ups", "gen", "trafo", "busway", "it_busbar", "before_ups_busbar"),
    )

    # เก็บผลไว้ให้ tab อื่น (เช่น tab 4 SLD) เรียกใช้ได้ต่อ โดยไม่ต้องคำนวณซ้ำ
    st.session_state.sizing_group_calcs = group_calcs
    st.session_state.sizing_common_sizes = common_sizes

    st.info(
        f"🔧 ใช้ขนาดเดียวกันทุกกลุ่ม (เลือกจากค่าที่มากสุด) — "
        f"UPS: {common_sizes['ups']:,.0f} kW  |  "
        f"Transformer: {common_sizes['trafo']:,.0f} kVA  |  "
        f"Generator: {common_sizes['gen']:,.0f} kW  |  "
        f"Busway: {common_sizes['busway']:,.0f} A"
        if all(v is not None for v in common_sizes.values())
        else "⚠️ บางกลุ่มไม่มี size รองรับ — ตรวจสอบ Standard Size List"
    )

    # ── PASS 2: render ผลลัพธ์ที่ override ขนาดเป็นค่าร่วมแล้ว ──
    for gc in group_calcs:
        gi    = gc["gi"]
        chain = gc["chain"]
        equip = gc["equip"]

        badge_color = GROUP_BADGE_COLORS[(gi - 1) % len(GROUP_BADGE_COLORS)]
        st.markdown(
            f'<div style="background:{badge_color};padding:8px 16px;border-radius:8px;'
            f'font-size:15px;font-weight:700;margin-bottom:10px">Generator Group {gi}</div>',
            unsafe_allow_html=True,
        )

        # ── ส่วนที่ 1: Load Chain Table ─────────────────────────
        st.markdown("**Load Chain**")
        n_chain = chain["normal"]
        f_chain = chain["fault"]

        chain_rows = [
            ("1",  "Max IT Load per UPS",                    n_chain["it_kw"],         f_chain["it_kw"]),
            ("2",  "+ Transmission Loss (×" + f"{(1+cfg['tx_loss']):.3f}" + ")",
                                                              n_chain["connected_it"] - n_chain["it_kw"],
                                                              f_chain["connected_it"] - f_chain["it_kw"]),
            ("2",  "= Connected IT Load  →  🔲 เลือก UPS",  n_chain["connected_it"],  f_chain["connected_it"]),
            ("3",  "+ UPS Loss",                             n_chain["ups_loss"],      f_chain["ups_loss"]),
            ("3",  "+ UPS Battery Charging",                 n_chain["ups_charging"],  f_chain["ups_charging"]),
            ("3",  "= Total UPS Output",                     n_chain["ups_total_out"], f_chain["ups_total_out"]),
            ("4",  "+ HVAC Load in PTU",                     n_chain["hvac"],          f_chain["hvac"]),
            ("4",  "= Total PTU Load (kW)",                  n_chain["ptu_kw"],        f_chain["ptu_kw"]),
            ("4",  "= Total PTU Load (kVA)",
                                                              n_chain["ptu_kva"],       f_chain["ptu_kva"]),
            ("5",  "+ Transmission Loss (×" + f"{(1+cfg['tx_loss']):.3f}" + ")",
                                                              n_chain["total_connected"] - n_chain["ptu_kw"],
                                                              f_chain["total_connected"] - f_chain["ptu_kw"]),
            ("5",  "= Total Connected Load (kW)  →  🔲 เลือก Generator",
                                                              n_chain["total_connected"], f_chain["total_connected"]),
            ("5",  "= Total Connected Load (kVA)  →  🔲 เลือก Transformer",
                                                              n_chain["total_connected_kva"], f_chain["total_connected_kva"]),
            ("6",  "Actual Ampere",                          n_chain["actual_amp"],    f_chain["actual_amp"]),
            ("6",  "Design Ampere (×" + f"{cfg['design_margin']:.2f}" + ")  →  🔲 เลือก Busway",
                                                              n_chain["design_amp"],    f_chain["design_amp"]),
        ]

        chain_df = pd.DataFrame(chain_rows, columns=["Step", "Description", "Normal", "Fault (Worst Case)"])
        chain_df["Normal"]             = chain_df["Normal"].apply(lambda x: f"{x:,.1f}")
        chain_df["Fault (Worst Case)"] = chain_df["Fault (Worst Case)"].apply(lambda x: f"{x:,.1f}")
        st.dataframe(chain_df, use_container_width=True, hide_index=True)

        # ── ส่วนที่ 2: Equipment Card ────────────────────────────
        st.markdown("**Equipment Selection (4 sets — 4N3)**")
        eq_cols = st.columns(4)
        eq_items = [
            ("UPS",         equip["ups"],    "kW"),
            ("Transformer", equip["trafo"],  "kVA"),
            ("Generator",   equip["gen"],    "kW"),
            ("Busway",      equip["busway"], "A"),
        ]
        for col, (name, eq, unit) in zip(eq_cols, eq_items):
            with col:
                size_str = f"{eq['size']:,.0f} {unit}" if eq["size"] else "❌ N/A"
                load_str = f"{eq['load']:,.1f} {unit}"
                st.markdown(
                    f'<div style="border:1px solid #E5E7EB;border-radius:8px;padding:12px;background:white">'
                    f'<div style="font-size:13px;font-weight:700;color:#1F4E79;margin-bottom:6px">{name}</div>'
                    f'<div style="font-size:20px;font-weight:700">{size_str}</div>'
                    f'<div style="font-size:11px;color:#666;margin:4px 0">Max Load: {load_str}</div>'
                    f'{util_bar_html(eq["util"], cfg["util_threshold"])}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # เก็บสำหรับ Summary
        summary_rows.append({
            "กลุ่ม":           f"G{gi}",
            "UPS (kW)":        f"{equip['ups']['size']:,.0f}"   if equip["ups"]["size"]    else "N/A",
            "UPS Util%":       f"{equip['ups']['util']*100:.1f}%"   if equip["ups"]["util"]    else "—",
            "Trafo (kVA)":     f"{equip['trafo']['size']:,.0f}" if equip["trafo"]["size"]  else "N/A",
            "Trafo Util%":     f"{equip['trafo']['util']*100:.1f}%" if equip["trafo"]["util"]  else "—",
            "Generator (kW)":  f"{equip['gen']['size']:,.0f}"   if equip["gen"]["size"]    else "N/A",
            "Gen Util%":       f"{equip['gen']['util']*100:.1f}%"   if equip["gen"]["util"]    else "—",
            "Busway (A)":      f"{equip['busway']['size']:,.0f}" if equip["busway"]["size"] else "N/A",
        })

        st.divider()

    # ── SECTION: Comparison Summary ─────────────────────────────
    st.header("📊 Comparison Summary — ทุกกลุ่ม")
    st.caption("ใช้เป็นฐานคำนวณขนาดอุปกรณ์จริงหน้างาน | UPS/Transformer/Generator/Busway ใช้ขนาดเดียวกันทุกกลุ่ม (เลือกจากค่ามากสุด)")
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

#เชื่อมระบบ

