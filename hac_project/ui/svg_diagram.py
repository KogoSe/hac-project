"""
SVG DIAGRAM BUILDER — วาด HAC layout พร้อมระบายสีกลุ่ม
"""
from constants import GROUP_SVG_COLORS


def build_hac_svg(hac_list: list[dict], groups: list[list] = None) -> str:
    """
    วาด SVG แสดง HAC layout พร้อมระบายสีกลุ่ม
    hac_list: list of {name, count, load, source_type}
    """
    FIXED_WIDTH    = 1000
    BOX_HEIGHT     = 60
    CONN_HEIGHT    = 50
    ROW_GAP        = 50
    SIDE_MARGIN    = 20
    LABEL_FONT     = 18
    CONN_FONT      = 12
    CONN_PAD_RATIO = 0.25

    # build row → group color map
    row_color_map = {}
    if groups:
        for gi, grp in enumerate(groups):
            color = GROUP_SVG_COLORS[gi % len(GROUP_SVG_COLORS)]
            for row in grp:
                row_color_map[(row["hac"], row["side"])] = color

    inner_width  = FIXED_WIDTH - 2 * SIDE_MARGIN
    total_height = len(hac_list) * (BOX_HEIGHT + 2 * CONN_HEIGHT) + (len(hac_list) - 1) * ROW_GAP + 40

    parts = [
        f'<svg viewBox="0 0 {FIXED_WIDTH} {total_height}" width="100%" height="auto" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Arial, sans-serif">',
        f'<rect x="0" y="0" width="{FIXED_WIDTH}" height="{total_height}" fill="#f8f9fa"/>',
    ]

    y = 20
    for hac in hac_list:
        count      = int(hac["count"])
        load       = hac["load"]
        name       = hac["name"]
        is_4src    = hac.get("source_type", "2-source") == "4-source"
        cell_w     = inner_width / count
        conn_w     = cell_w * (1 - CONN_PAD_RATIO)
        conn_pad   = cell_w * CONN_PAD_RATIO / 2
        top_color  = row_color_map.get((name, "บน"),   "white")
        bot_color  = row_color_map.get((name, "ล่าง"), "white")
        # 4-source ขอบเส้นหนาสีม่วง, 2-source ปกติ
        stroke_col = "#7C3AED" if is_4src else "#555"
        stroke_w   = "2.5"    if is_4src else "1.5"

        top_y = y
        box_y = top_y + CONN_HEIGHT
        bot_y = box_y + BOX_HEIGHT

        # rack_loads: ใช้ rack_list ถ้ามี ไม่งั้น fallback เป็น load เดิม
        rack_loads = hac.get("rack_list", [load] * count)
        if len(rack_loads) != count:
            rack_loads = [load] * count

        for side_y, fill in [(top_y, top_color), (bot_y, bot_color)]:
            for i in range(count):
                cx = SIDE_MARGIN + i * cell_w + conn_pad
                label = f"{rack_loads[i]:g}" if i < len(rack_loads) else f"{load:g}"
                parts.append(
                    f'<rect x="{cx:.1f}" y="{side_y}" width="{conn_w:.1f}" height="{CONN_HEIGHT}" '
                    f'fill="{fill}" stroke="{stroke_col}" stroke-width="{stroke_w}" rx="2"/>'
                )
                parts.append(
                    f'<text x="{cx + conn_w/2:.1f}" y="{side_y + CONN_HEIGHT/2 + 5}" '
                    f'font-size="{CONN_FONT}" text-anchor="middle" fill="#333">{label}</text>'
                )

        # label badge สำหรับ 4-source
        src_label = " [4-source]" if is_4src else ""
        parts.append(
            f'<rect x="{SIDE_MARGIN}" y="{box_y}" width="{inner_width}" height="{BOX_HEIGHT}" '
            f'fill="white" stroke="#1a1a1a" stroke-width="2.5" rx="3"/>'
        )
        parts.append(
            f'<text x="{FIXED_WIDTH/2}" y="{box_y + BOX_HEIGHT/2 + 7}" '
            f'font-size="{LABEL_FONT}" font-weight="bold" text-anchor="middle" fill="#1a1a1a">'
            f'{name}{src_label}</text>'
        )
        y = bot_y + CONN_HEIGHT + ROW_GAP

    parts.append("</svg>")
    return "".join(parts)
