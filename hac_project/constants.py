# ═══════════════════════════════════════════════════════════════
# CONSTANTS — ใช้ร่วมกันทั้ง engine และ ui
# ═══════════════════════════════════════════════════════════════

UPS_UNITS      = ["A", "B", "C", "D"]  # default 4 ตัวต่อกลุ่ม — ใช้เป็น fallback เมื่อไม่ได้ระบุ n_ups_per_group
N_UPS_PER_GROUP_OPTIONS = [4, 5, 6]     # ตัวเลือกจำนวน UPS ต่อกลุ่มที่รองรับ (default = 4)
PAIR_ROTATION  = ["AB", "CD", "AC", "BD", "AD", "BC"]  # non-overlapping rotation (เฉพาะกรณี n=4, legacy/ไม่ได้ใช้จริงแล้ว)
SOURCE_OPTIONS = ["2-source", "4-source"]


def get_group_ups_units(n_ups_per_group: int) -> list:
    """
    รายชื่อ UPS ภายในกลุ่ม (ตัวอักษร A, B, C, ... ยาวตาม n_ups_per_group) — ใช้เป็น "key คำนวณ"
    ภายใน engine เท่านั้น (คนละเรื่องกับ ups_display_label ที่ไล่ตัวอักษรต่อเนื่องข้ามกลุ่มสำหรับแสดงผล)
    """
    import string
    return list(string.ascii_uppercase[:n_ups_per_group])

PAIR_COLORS = {
    "AB": "#B5D4F4", "AC": "#9FE1CB", "AD": "#C0DD97",
    "BC": "#FAC775", "BD": "#F4C0D1", "CD": "#F5C4B3",
    "ABCD": "#E9D5FF",  # 4-source
}
GROUP_BADGE_COLORS = ["#DBEAFE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#F3E8FF"]
GROUP_SVG_COLORS   = ["#DBEAFE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#F3E8FF"]


def ups_display_label(gi: int, u: str, n_ups_per_group: int = 4) -> str:
    """
    ชื่อ UPS ที่ใช้แสดงผลจริง (ไล่ตัวอักษรต่อเนื่องข้ามกลุ่ม) — เช่น n_ups_per_group=4: กลุ่ม 1 = A,B,C,D,
    กลุ่ม 2 = E,F,G,H, ... | n_ups_per_group=5: กลุ่ม 1 = A,B,C,D,E, กลุ่ม 2 = F,G,H,I,J, ...
    ภายใน engine ยังใช้ A,B,C,... (จาก get_group_ups_units) เป็น key คำนวณเหมือนกันทุกกลุ่มเสมอ
    ฟังก์ชันนี้แปลงเฉพาะตอนแสดงผลให้ผู้ใช้เห็นเท่านั้น (ทุกกลุ่มต้องมี n_ups_per_group เท่ากัน
    เป็น setting เดียวกันทั้งโปรเจกต์ — ไม่รองรับกลุ่มที่มีจำนวน UPS ไม่เท่ากัน)
    """
    import string
    group_units = get_group_ups_units(n_ups_per_group)
    idx = (gi - 1) * n_ups_per_group + group_units.index(u)
    return string.ascii_uppercase[idx % 26]


# ── SLD DEFAULT VALUES (tab 4) ────────────────────────────────
# PTU_FIX: 33 attributes พร้อม default value ตามรูป
PTU_FIX_DEFAULTS = [
    # (attribute_name, default_value)
    ("RMU_LEFT_FROMMV",       "FROM MV.SWG.XX"),
    ("RMU_RIGHT_FROMMV",      "FROM MV.SWG.XX"),
    ("RMU_LEFT_CB",           "630"),
    ("RMU_RIGHT_LB",          "630"),
    ("RMU_BUSBAR",            "CU BUSBAR 630A"),
    ("RMU_CB",                "200"),
    ("RMU_S_GROUNDCABLE",     "IEC01 240 Sq.mm. IN PVC %%C50 mm."),
    ("TX_S_RATING",           "2.25 MVA DRY TYPE (IP00) 22/0.4 kV, K-4 RATED"),
    ("TX_S_BUSWAY",           "4000A BUSWAY AL. IP 55 (BY PTU)"),
    ("TX_S_GROUNDCABLE",      "IEC01 2x240 Sq.mm. IN PVC %%C80 mm."),
    ("GEN_S_RATING",          "2MW/2.5MVA 400V,3%%C, 50Hz GENERATOR"),
    ("GEN_GCP",               "400V, 3%%C, 50Hz 65kA FROM 3B"),
    ("GEN_S_BUSBARRATING",    "4000A CU, BUS BAR 100%N, 25%G, 3P 4W"),
    ("GEN_LEFT_ACB",          "4000AT 4000AF 4P, ACB, LSI (NC)"),
    ("GEN_RIGHT_ACB",         "4000AT 4000AF 4P, ACB, LSI (NO)"),
    ("GEN_S_BASWAYTOPTU",     "4000A BUSWAY AL. IP 68"),
    ("GEN_S_GROUNDCABLE",     "IEC01 2x240 Sq.mm. IN PVC 080 mm."),
    ("PTU_IF01",              "4000AT 4000AF 4P, ACB LSI (NC)"),
    ("PTU_IF02",              "4000AT 4000AF 4P, ACB LSI (NO)"),
    ("PTU_MAINBUSBAR",        "4000A CU, BUS BAR 100%N, 25%G, 3P 4W"),
    ("PTU_BUSBARBEFOREUPS",   "4000A CU, BUS BAR 100%N, 25%G, 3P 4W"),
    ("PTU_GROUNDCABLE",       "IEC01 2x240 Sq.mm. IN PVC %%C80 mm."),
    ("CB_BUSBARBEFOREUPS",    "4000AT 4000AF 4P, ACB LSI (NC)"),
    ("CB_FROMGEN",            "400AT 400AF 4P, ACB LSI (NO)"),
    ("UPS_RATING",            "2000kW"),
    ("UPS_EOL",               "EOL 10 MINS Li-Ion BATT EOL"),
    ("BATT.",                 "XX"),
    ("OUPS_ITBUSBAR_IF02",    "4000A CU, BUS BAR 100%N, 25%G, 3P 4W"),
    ("OUPS_CB_ITOF01",        "2000AT 2000AF TPN, ACB, LSI (NC)"),
    ("OUPS_CB_ITOF02",        "2000AT 2000AF TPN, ACB, LSI (NC)"),
    ("OUPS_MAINITBUSBAR",     "4000A CU. BUSBAR 100%N, 25%G. : 3P 4W"),
    ("OUPS_CB_ITIF01",        "4000AT 4000AF 4P, ACB LSI (NO)"),
    ("OUPS_CB_ITIF02",        "4000AT 4000AF TPN, ACB LSI (NC)"),
    ("OUPS_CB_ITIF03",        "4000AT 4000AF TPN, ACB, LSI (NO)"),
    ("FINALBUSBAR01",         "2000A BUSWAY AL. IP 68"),
    ("FINALBUSBAR02",         "2000A BUSWAY AL. IP 68"),
    ("FINALBUSBAR03",         "2000A BUSWAY AL. IP 68"),
]

# MDBAUX: 1 attribute
MDBAUX_DEFAULTS = [
    ("CB_MCCB_BLOCK", "100AT\n100AF\nTPN, \nMCCB,\nLSI (NO)"),
]

# SPARE: 1 attribute
SPARE_DEFAULTS = [
    ("CB_MCCB_BLOCK_SPARE", "630AT\n630AF\nTPN, \nMCCB,\nLSI (NO)"),
]


# ── SVG (Active Harmonic Filter) SIZING (tab 7) ─────────────────
# NOTE: placeholder list from KogoSe — replace with confirmed manufacturer
# catalog when available. IEEE-519 TDD table itself lives in engine/harmonic.py
# since it's the calculation logic, not a project-specific assumption.
SVG_STANDARD_SIZES = [25, 30, 50, 75, 100, 150, 200, 300, 400, 500, 600]  # Ampsd
