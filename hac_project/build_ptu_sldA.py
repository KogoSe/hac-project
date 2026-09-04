"""
build_ptu_sld.py — สร้าง Single Line Diagram ของ PTU จาก block (PTU_FIX, MDBAUX, SPARE)

วิธีใช้: แก้ค่าตัวแปรในโซน "==== แก้ค่าตรงนี้ ====" ด้านล่างได้เลย
- FEEDER_LIST: รายการ feeder ที่จะ insert (เรียงซ้ายไปขวา) ลบ/เพิ่มรายการได้ตามใจ
- PTU_FIX_OVERRIDES: ค่า attribute ของ PTU_FIX ที่ต้องการเปลี่ยนจาก default
  ตัวไหนไม่ใส่ในนี้ = ใช้ค่า default ที่วาดไว้ในบล็อกอัตโนมัติ
  ถ้าอยากให้ค่าขึ้นหลายบรรทัด (multiline attribute เช่น GEN_S_RATING, TX_S_RATING)
  ให้ใช้ "\\n" คั่นตรงจุดที่อยากขึ้นบรรทัดใหม่ได้เลย (ดูตัวอย่างด้านล่าง)

หลักการ:
- PTU_FIX          insert ที่ (0,0) ครั้งเดียว (โครงสร้าง static ทั้งหมด)
- Main busbar      Python วาดเป็นเส้นตรง เริ่มจาก BUSBAR_START ยาวไปทางขวา
- MDBAUX / SPARE   insert ซ้ำตามจำนวนที่ต้องการ เริ่มจาก FEEDER_START_X เรียงห่างกันตาม
                   FEEDER_PITCH แต่ละตัวแก้ค่า attribute ได้อิสระ
"""

import ezdxf
from ezdxf.addons import Importer

SOURCE_FILE = "PTU_TEST.dxf"
OUTPUT_FILE = "ptu_sample_sld.dxf"

BUSBAR_START = (-51498.0, 19778.0)  # จุดเริ่มเส้น busbar (z=0) ลากไปทางขวา
FEEDER_START_X = -19500.0           # จุดเริ่ม insert MDBAUX/SPARE ตัวแรก (y ใช้ตัวเดียวกับ busbar)
FEEDER_PITCH = 4100.0               # ระยะห่างระหว่าง MDBAUX/SPARE แต่ละตัว (ปัดจากของจริง 4087.41)
WIRE_LAYER = "E-SGL"

# ATTDEF tag ของแต่ละ block (ใช้ตอนแก้ค่า attribute หลัง insert)
ATTR_TAGS = {
    "MDBAUX": "CB_MCCB_BLOCK",
    "SPARE":  "CB_MCCB_BLOCK_SPARE",
}

# =============================================================================
# ==== แก้ค่าตรงนี้ ====
# =============================================================================

# รายการ feeder ที่จะ insert เรียงจากซ้ายไปขวาตามลำดับใน list
# type: "MDBAUX" หรือ "SPARE" | label: ข้อความ CB rating ที่จะโชว์
FEEDER_LIST = [
    {"type": "MDBAUX", "label": "100AT 100AF TPN, MCCB, LSI (NO)"},
    {"type": "MDBAUX", "label": "250AT 250AF TPN, MCCB, LSI (NO)"},
    {"type": "SPARE",  "label": "630AT 630AF TPN, MCCB, LSI (NO)"},
    {"type": "MDBAUX", "label": "400AT 400AF TPN, MCCB, LSI (NO)"},
    {"type": "SPARE",  "label": "630AT 630AF TPN, MCCB, LSI (NO)"},
]

# ค่า attribute ของ PTU_FIX ที่ต้องการ "เขียนทับ" default (tag: ค่าใหม่)
# tag ไหนไม่ใส่ในนี้ = ใช้ default text ที่วาดไว้ในบล็อกเองอัตโนมัติ (ขึ้นหลายบรรทัดถูกต้อง)
# ถ้าจะ override attribute ที่เป็น multiline (เช่น GEN_S_RATING, TX_S_RATING)
# ใช้ "\n" คั่นบรรทัดในสตริงได้เลย จะถูกแปลงเป็นการขึ้นบรรทัดใหม่จริงในแบบ
PTU_FIX_OVERRIDES = {
    "TX_S_RATING": "2.5 MVA DRY TYPE (IP00) 22/0.4 kV, K-4 RATED,\nAL/AL 3P,4W, DYN11, %UK6, 50Hz",
    "UPS_RATING": "2500kW",
    # "GEN_S_RATING": "2.5MW/3.1MVA 400V,3P, 50Hz\nGENERATOR SET CLASS G3,\nRATING SHALL COMPLY ANNUAL\nUNLIMITED RUNTIME.",
}

# =============================================================================
# ==== โค้ดส่วนวาด (ปกติไม่ต้องแก้ตรงนี้) ====
# =============================================================================


def set_attrib_text(blockref, tag, new_text):
    """แก้ค่า attribute ของ block ที่ insert ไปแล้ว"""
    for attrib in blockref.attribs:
        if attrib.dxf.tag == tag:
            attrib.dxf.text = new_text
            return True
    return False


def fix_multiline_attribs(blockref, overrides):
    """แก้ปัญหา ezdxf add_auto_attribs() ที่ flatten multiline attribute
    (attribute ที่มี embedded MTEXT ข้างใน เช่น GEN_S_RATING, TX_S_RATING) ให้
    กลายเป็นแถวเดียวยาวเสมอ ไม่ว่าจะ override หรือปล่อย default ก็ตาม

    ทำงานหลัง add_auto_attribs() แล้ว: ไล่ดู ATTRIB ที่เพิ่งสร้าง เทียบกับ ATTDEF
    ต้นฉบับ ถ้า ATTDEF ตัวไหนเป็น multiline (has_embedded_mtext_entity) จะ
    - ถ้ามีใน overrides: แปลง "\\n" ในค่าที่พี่ใส่ เป็นการขึ้นบรรทัดใหม่จริง (\\P)
    - ถ้าไม่มีใน overrides (ใช้ default): เอาการขึ้นบรรทัดเดิมจาก ATTDEF กลับมาคืน
    """
    block_layout = blockref.block()
    if block_layout is None:
        return
    attdefs = {a.dxf.tag: a for a in block_layout.attdefs()}

    for attrib in blockref.attribs:
        tag = attrib.dxf.tag
        attdef = attdefs.get(tag)
        if attdef is None or not attdef.has_embedded_mtext_entity:
            continue  # attribute ธรรมดา ไม่ใช่ multiline ไม่ต้องแตะ

        if tag in overrides:
            new_value = overrides[tag]
            mtext_str = new_value.replace("\n", "\\P")
            flat_str = new_value.replace("\n", " ")
        else:
            # คืนค่าการขึ้นบรรทัดเดิมจาก ATTDEF ต้นฉบับ
            mtext_str = attdef.virtual_mtext_entity().text
            flat_str = attdef.dxf.text

        mtext = attdef.virtual_mtext_entity()
        mtext.text = mtext_str
        attrib.embed_mtext(mtext)
        attrib.dxf.text = flat_str


def fix_attrib_placement(blockref):
    """
    แก้ปัญหา ezdxf add_auto_attribs() ที่บางครั้งไม่ transform 'align_point'
    ของ ATTRIB ให้ตรงกับตำแหน่งจริงใน ATTDEF ต้นฉบับ — เกิดกับ attribute ที่
    justify ไม่ใช่ baseline-left ธรรมดา (เช่น Top Left, Middle Center)
    """
    block_layout = blockref.block()
    if block_layout is None:
        return
    attdefs = {a.dxf.tag: a for a in block_layout.attdefs()}
    m = blockref.matrix44()

    for attrib in blockref.attribs:
        attdef = attdefs.get(attrib.dxf.tag)
        if attdef is None:
            continue
        attrib.dxf.halign = attdef.dxf.halign
        attrib.dxf.valign = attdef.dxf.valign
        attrib.dxf.insert = m.transform(attdef.dxf.insert)
        if attdef.dxf.halign != 0 or attdef.dxf.valign != 0:
            align_src = attdef.dxf.align_point if attdef.dxf.hasattr("align_point") else attdef.dxf.insert
            attrib.dxf.align_point = m.transform(align_src)


def build_ptu_sld(feeder_list, ptu_fix_overrides=None):
    """
    feeder_list: list ของ dict เช่น
        [{"type": "MDBAUX", "label": "100AT 100AF TPN, MCCB, LSI (NO)"}, ...]
        เรียงจากซ้ายไปขวาตามลำดับใน list
    ptu_fix_overrides: dict {tag: ค่าใหม่} สำหรับ attribute ของ PTU_FIX
        tag ไหนไม่ใส่ = ใช้ default ของบล็อกเอง (รวมถึงคง multiline เดิมไว้)
    """
    ptu_fix_overrides = ptu_fix_overrides or {}

    src_doc = ezdxf.readfile(SOURCE_FILE)

    doc = ezdxf.new(src_doc.dxfversion)
    if WIRE_LAYER not in doc.layers:
        doc.layers.add(name=WIRE_LAYER, color=4)

    importer = Importer(src_doc, doc)
    importer.import_blocks(block_names=["PTU_FIX", "MDBAUX", "SPARE"])
    importer.finalize()

    msp = doc.modelspace()

    # 1) วาง PTU_FIX ที่ (0,0) — โครงสร้าง static ทั้งหมด
    #    ต้องเรียก add_auto_attribs() เสมอ ไม่งั้น attribute ทั้งหมดจะไม่ถูกสร้างขึ้นมาเลย
    ptu_fix_ref = msp.add_blockref("PTU_FIX", (0, 0), dxfattribs={"layer": "0"})
    ptu_fix_ref.add_auto_attribs(ptu_fix_overrides)
    fix_multiline_attribs(ptu_fix_ref, ptu_fix_overrides)
    fix_attrib_placement(ptu_fix_ref)

    # 2) วาง MDBAUX/SPARE เรียงต่อจาก FEEDER_START_X ไปทางขวา (y เดียวกับ busbar)
    y0 = BUSBAR_START[1]
    for i, feeder in enumerate(feeder_list):
        insert_point = (FEEDER_START_X + i * FEEDER_PITCH, y0)
        blk_name = feeder["type"]

        blockref = msp.add_blockref(blk_name, insert_point, dxfattribs={"layer": "0"})
        blockref.add_auto_attribs({ATTR_TAGS[blk_name]: feeder["label"]})
        fix_multiline_attribs(blockref, {ATTR_TAGS[blk_name]: feeder["label"]})
        fix_attrib_placement(blockref)

    # 3) วาด busbar เส้นเดียว เริ่มจาก BUSBAR_START ยาวไปทางขวาถึง feeder ตัวสุดท้าย
    x0, y0 = BUSBAR_START
    if feeder_list:
        busbar_end_x = FEEDER_START_X + (len(feeder_list) - 1) * FEEDER_PITCH
    else:
        busbar_end_x = x0
    msp.add_line(
        (x0, y0), (busbar_end_x, y0),
        dxfattribs={"layer": WIRE_LAYER, "lineweight": 50},
    )

    doc.saveas(OUTPUT_FILE)
    print(f"สร้าง {OUTPUT_FILE} แล้ว — {len(feeder_list)} feeder, busbar ยาว {busbar_end_x - x0:.0f} หน่วย")


if __name__ == "__main__":
    build_ptu_sld(FEEDER_LIST, PTU_FIX_OVERRIDES)


# =============================================================================
# ==== run_from_streamlit — เรียกจาก ptu_v7.py โดยตรง ไม่ต้องแตะโค้ดเดิม ====
# =============================================================================

def run_from_streamlit(feeder_list: list, ptu_fix_overrides: dict = None) -> bytes:
    """
    เหมือน build_ptu_sld() ทุกอย่าง แต่ return .dxf เป็น bytes
    แทนที่จะ saveas ลง disk เพื่อให้ Streamlit download ได้ทันที

    feeder_list: list ของ dict {"type": "MDBAUX"|"SPARE", "label": "..."}
    ptu_fix_overrides: dict {tag: ค่าใหม่} เฉพาะตัวที่ต้องการ override
    """
    import io
    ptu_fix_overrides = ptu_fix_overrides or {}

    src_doc = ezdxf.readfile(SOURCE_FILE)

    doc = ezdxf.new(src_doc.dxfversion)
    if WIRE_LAYER not in doc.layers:
        doc.layers.add(name=WIRE_LAYER, color=4)

    importer = Importer(src_doc, doc)
    importer.import_blocks(block_names=["PTU_FIX", "MDBAUX", "SPARE"])
    importer.finalize()

    msp = doc.modelspace()

    # 1) วาง PTU_FIX ที่ (0,0)
    ptu_fix_ref = msp.add_blockref("PTU_FIX", (0, 0), dxfattribs={"layer": "0"})
    ptu_fix_ref.add_auto_attribs(ptu_fix_overrides)
    fix_multiline_attribs(ptu_fix_ref, ptu_fix_overrides)
    fix_attrib_placement(ptu_fix_ref)

    # 2) วาง MDBAUX/SPARE เรียงต่อจาก FEEDER_START_X
    y0 = BUSBAR_START[1]
    for i, feeder in enumerate(feeder_list):
        insert_point = (FEEDER_START_X + i * FEEDER_PITCH, y0)
        blk_name = feeder["type"]
        blockref = msp.add_blockref(blk_name, insert_point, dxfattribs={"layer": "0"})
        blockref.add_auto_attribs({ATTR_TAGS[blk_name]: feeder["label"]})
        fix_multiline_attribs(blockref, {ATTR_TAGS[blk_name]: feeder["label"]})
        fix_attrib_placement(blockref)

    # 3) วาด busbar
    x0, y0 = BUSBAR_START
    busbar_end_x = FEEDER_START_X + (len(feeder_list) - 1) * FEEDER_PITCH if feeder_list else x0
    msp.add_line(
        (x0, y0), (busbar_end_x, y0),
        dxfattribs={"layer": WIRE_LAYER, "lineweight": 50},
    )

    # 4) return bytes แทน saveas
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as tmp:
        tmp_path = tmp.name
    doc.saveas(tmp_path)
    with open(tmp_path, 'rb') as f:
        dxf_bytes = f.read()
    os.unlink(tmp_path)
    return dxf_bytes
