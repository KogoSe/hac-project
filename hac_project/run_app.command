#!/bin/bash
# ============================================================
# run_app.command — ดับเบิลคลิกเพื่อรัน HAC Load Designer บน Mac
# วางไฟล์นี้ไว้ที่ hac_project/ (ระดับเดียวกับ app.py)
# ============================================================

# cd ไปที่โฟลเดอร์ของไฟล์นี้เอง (ไม่ว่าจะดับเบิลคลิกจากไหนก็ตาม)
cd "$(dirname "$0")"

echo "============================================"
echo "  HAC Load Designer — เริ่มต้นระบบ"
echo "============================================"
echo ""

# ── ตรวจสอบว่ามี app.py อยู่จริงไหม ──────────────────────────
if [ ! -f "app.py" ]; then
    echo "❌ ไม่พบ app.py ในโฟลเดอร์นี้"
    echo "   ต้องวางไฟล์ run_app.command นี้ไว้ที่เดียวกับ app.py"
    echo ""
    read -p "กด Enter เพื่อปิดหน้าต่างนี้..."
    exit 1
fi

# ── หา Python ที่จะใช้ ──────────────────────────────────────
PYTHON_CMD=""

if [ -d ".venv" ] && [ -f ".venv/bin/python3" ]; then
    echo "🔍 พบ virtual environment (.venv) — ใช้ตัวนี้"
    source .venv/bin/activate
    PYTHON_CMD="python3"
elif [ -d "venv" ] && [ -f "venv/bin/python3" ]; then
    echo "🔍 พบ virtual environment (venv) — ใช้ตัวนี้"
    source venv/bin/activate
    PYTHON_CMD="python3"
elif command -v python3 &> /dev/null; then
    echo "🔍 ไม่พบ venv — ใช้ python3 ของเครื่อง"
    PYTHON_CMD="python3"
else
    echo "❌ ไม่พบ Python 3 ในเครื่องเลย"
    echo "   ต้องติดตั้ง Python 3 ก่อน (https://www.python.org/downloads/)"
    echo ""
    read -p "กด Enter เพื่อปิดหน้าต่างนี้..."
    exit 1
fi

echo "✅ ใช้: $($PYTHON_CMD --version)"
echo ""

# ── เช็คว่ามี streamlit ติดตั้งหรือยัง ────────────────────────
if ! $PYTHON_CMD -m streamlit --version &> /dev/null; then
    echo "⚠️  ยังไม่มี streamlit ในเครื่อง — กำลังติดตั้งให้อัตโนมัติ..."
    echo ""
    if [ -f "requirements.txt" ]; then
        $PYTHON_CMD -m pip install -r requirements.txt
    else
        $PYTHON_CMD -m pip install streamlit pandas openpyxl ezdxf
    fi
    echo ""
fi

# ── รัน Streamlit ───────────────────────────────────────────
echo "🚀 กำลังเปิด HAC Load Designer..."
echo "   (ถ้า browser ไม่เปิดเอง ให้เปิดลิงก์ที่ขึ้นด้านล่างนี้ด้วยตัวเอง)"
echo ""
$PYTHON_CMD -m streamlit run app.py

# ── ถ้า streamlit ปิดตัวหรือ error ค้างหน้าต่างไว้ให้อ่าน ─────
echo ""
echo "============================================"
echo "  โปรแกรมปิดแล้ว"
echo "============================================"
read -p "กด Enter เพื่อปิดหน้าต่างนี้..."
