# ═══════════════════════════════════════════════════════════════
# CONSTANTS — ใช้ร่วมกันทั้ง engine และ ui
# ═══════════════════════════════════════════════════════════════

UPS_UNITS      = ["A", "B", "C", "D"]
PAIR_ROTATION  = ["AB", "CD", "AC", "BD", "AD", "BC"]  # non-overlapping rotation
SOURCE_OPTIONS = ["2-source", "4-source"]

PAIR_COLORS = {
    "AB": "#B5D4F4", "AC": "#9FE1CB", "AD": "#C0DD97",
    "BC": "#FAC775", "BD": "#F4C0D1", "CD": "#F5C4B3",
    "ABCD": "#E9D5FF",  # 4-source
}
GROUP_BADGE_COLORS = ["#DBEAFE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#F3E8FF"]
GROUP_SVG_COLORS   = ["#DBEAFE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#F3E8FF"]


# ── SLD DEFAULT VALUES (tab 4) ────────────────────────────────
# PTU_FIX: 33 attributes พร้อม default value ตามรูป
PTU_FIX_DEFAULTS = [
    # (attribute_name, default_value)
    ("RMU_LEFT_FROMMV",       "FROM MV.SWG.XX"),
    ("RMU_RIGHT_FROMMV",      "FROM MV.SWG.XX"),
    ("RMU_LEFT_CB",           "630"),
    ("RMU_RIGHT_LB",          "630"),
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
