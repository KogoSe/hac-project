"""
SVG DIAGRAM BUILDER — วาด HAC layout พร้อมระบายสีกลุ่ม
"""
import math

from constants import GROUP_SVG_COLORS, ups_display_label, get_group_ups_units


def build_hac_svg(hac_list: list[dict], groups: list[list] = None, n_ups_per_group: int = 4) -> str:
    """
    วาด SVG แสดง HAC layout พร้อมระบายสีกลุ่ม
    hac_list: list of {"name": str, "rows": [{"side": "บน"/"ล่าง", "rack_list": [...], "source_type": str}, ...]}
    แต่ละ HAC มีได้ 1 หรือ 2 แถว (rows) — ไม่ fix 2 แถวตายตัว, HAC แถวเดียวไม่เว้นช่องว่างแทนแถวที่ไม่มี
    ถ้ามี groups: แสดง pairing label (เช่น "AB", "ABCD") ทางซ้ายของแต่ละแถวด้วย
    """
    FIXED_WIDTH    = 1000
    BOX_HEIGHT     = 60
    CONN_HEIGHT    = 50
    ROW_GAP        = 50
    SIDE_MARGIN    = 20
    LABEL_MARGIN   = 45   # พื้นที่สำหรับ pairing label ทางซ้าย (เผื่อ "ABCD") — ใช้เฉพาะตอนมี groups
    LABEL_FONT     = 18
    CONN_FONT      = 12
    PAIR_FONT      = 12
    CONN_PAD_RATIO = 0.25

    # build row → group color map + pairing label map
    row_color_map = {}
    row_pair_map  = {}
    if groups:
        ups_units = get_group_ups_units(n_ups_per_group)
        for gi, grp in enumerate(groups):
            color = GROUP_SVG_COLORS[gi % len(GROUP_SVG_COLORS)]
            group_labels = {u: ups_display_label(gi + 1, u, n_ups_per_group) for u in ups_units}
            for row in grp:
                row_color_map[(row["hac"], row["side"])] = color
                pair = row.get("pair", "")
                row_pair_map[(row["hac"], row["side"])] = "".join(group_labels.get(ch, ch) for ch in pair)

    left_offset  = SIDE_MARGIN + (LABEL_MARGIN if groups else 0)
    inner_width  = FIXED_WIDTH - left_offset - SIDE_MARGIN

    # total_height คำนวณจากจำนวนแถวจริงต่อ HAC (1 หรือ 2 แถว) ไม่ fix ตายตัว
    total_height = 40
    for hac in hac_list:
        total_height += len(hac["rows"]) * CONN_HEIGHT + BOX_HEIGHT
    if len(hac_list) > 1:
        total_height += (len(hac_list) - 1) * ROW_GAP

    parts = [
        f'<svg viewBox="0 0 {FIXED_WIDTH} {total_height}" width="100%" height="auto" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Arial, sans-serif">',
        f'<rect x="0" y="0" width="{FIXED_WIDTH}" height="{total_height}" fill="#f8f9fa"/>',
    ]

    y = 20
    for hac in hac_list:
        name    = hac["name"]
        rows    = hac["rows"]
        is_4src = any(r.get("source_type", "2-source") == "4-source" for r in rows)
        # 4-source ขอบเส้นหนาสีม่วง, 2-source ปกติ
        stroke_col = "#7C3AED" if is_4src else "#555"
        stroke_w   = "2.5"    if is_4src else "1.5"

        top_entry = next((r for r in rows if r["side"] == "บน"), None)
        bot_entry = next((r for r in rows if r["side"] == "ล่าง"), None)

        top_y = y
        box_y = top_y + (CONN_HEIGHT if top_entry else 0)
        bot_y = box_y + BOX_HEIGHT

        for row_entry, side_y in [(top_entry, top_y), (bot_entry, bot_y)]:
            if row_entry is None:
                continue  # ไม่มีแถวนี้ (HAC ที่มีแถวเดียว) — ไม่วาด ไม่เว้นช่องว่าง
            side_name = row_entry["side"]
            rack_list = row_entry.get("rack_list", [])
            count     = len(rack_list)
            fill      = row_color_map.get((name, side_name), "white")

            if groups:
                pair_label = row_pair_map.get((name, side_name), "")
                if pair_label:
                    parts.append(
                        f'<text x="{SIDE_MARGIN + LABEL_MARGIN - 8:.1f}" y="{side_y + CONN_HEIGHT/2 + 4:.1f}" '
                        f'font-size="{PAIR_FONT}" text-anchor="end" font-weight="700" fill="#444">{pair_label}</text>'
                    )

            if count == 0:
                continue  # rack layout ว่าง/parse ไม่ได้ (มี warning แยกอยู่แล้วในหน้า input)

            cell_w   = inner_width / count
            conn_w   = cell_w * (1 - CONN_PAD_RATIO)
            conn_pad = cell_w * CONN_PAD_RATIO / 2
            for i in range(count):
                cx = left_offset + i * cell_w + conn_pad
                label = f"{math.ceil(rack_list[i])}"  # แสดงปัดขึ้นเป็นจำนวนเต็มเพื่อความสวยงาม — คำนวณจริงยังใช้ค่าทศนิยมเดิม
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
            f'<rect x="{left_offset}" y="{box_y}" width="{inner_width}" height="{BOX_HEIGHT}" '
            f'fill="white" stroke="#1a1a1a" stroke-width="2.5" rx="3"/>'
        )
        parts.append(
            f'<text x="{left_offset + inner_width/2:.1f}" y="{box_y + BOX_HEIGHT/2 + 7}" '
            f'font-size="{LABEL_FONT}" font-weight="bold" text-anchor="middle" fill="#1a1a1a">'
            f'{name}{src_label}</text>'
        )
        y = box_y + BOX_HEIGHT + (CONN_HEIGHT if bot_entry else 0) + ROW_GAP

    parts.append("</svg>")
    return "".join(parts)
