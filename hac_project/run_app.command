#!/bin/bash
# ============================================================
# run_app.command — ดับเบิลคลิกเพื่อรัน HAC Load Designer บน Mac
# วางไฟล์นี้ไว้ที่ hac_project/ (ระดับเดียวกับ app.py)
# เครื่องเปล่า: ติดตั้ง Python + library ให้อัตโนมัติ (ต้องมีอินเทอร์เน็ต)
# ============================================================

PY_VERSION="3.12.8"
PY_URL="https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg"
PY_NEW_BIN="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

# cd ไปที่โฟลเดอร์ของไฟล์นี้เอง (ไม่ว่าจะดับเบิลคลิกจากไหนก็ตาม)
cd "$(dirname "$0")"

fail() {
    echo ""
    read -p "กด Enter เพื่อปิดหน้าต่างนี้..."
    exit 1
}

# ลองรัน python ตัวที่ส่งมา ใช้ได้และเป็น 3.9+ หรือไม่
# (python3 ของ macOS เครื่องเปล่าเป็นแค่ตัวหลอกที่เด้งขอติดตั้ง Xcode Tools
#  จึงต้องลองรันจริง ไม่ใช้ command -v อย่างเดียว)
python_ok() {
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" &> /dev/null
}

echo "============================================"
echo "  HAC Load Designer — เริ่มต้นระบบ"
echo "============================================"
echo ""

# ── ตรวจสอบว่ามี app.py อยู่จริงไหม ──────────────────────────
if [ ! -f "app.py" ]; then
    echo "❌ ไม่พบ app.py ในโฟลเดอร์นี้"
    echo "   ต้องวางไฟล์ run_app.command นี้ไว้ที่เดียวกับ app.py"
    fail
fi

# ── สร้าง .venv ถ้ายังไม่มี ──────────────────────────────────
if [ ! -x ".venv/bin/python3" ]; then
    BASE_PY=""
    for cand in "$PY_NEW_BIN" /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
        if command -v "$cand" &> /dev/null && python_ok "$cand"; then
            BASE_PY="$cand"
            break
        fi
    done

    # ไม่มี Python -> ดาวน์โหลดตัวติดตั้งทางการจาก python.org
    if [ -z "$BASE_PY" ]; then
        echo "⚠️  ไม่พบ Python 3 ในเครื่อง — กำลังดาวน์โหลดและติดตั้ง Python $PY_VERSION ให้อัตโนมัติ"
        echo "   (ต้องมีอินเทอร์เน็ต และจะถามรหัสผ่านเครื่อง Mac ของคุณ 1 ครั้ง)"
        echo ""
        PKG="$(mktemp -d)/python.pkg"
        if ! curl -fL --progress-bar -o "$PKG" "$PY_URL"; then
            echo "❌ ดาวน์โหลด Python ไม่สำเร็จ — ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่"
            echo "   หรือติดตั้งเองจาก https://www.python.org/downloads/"
            fail
        fi
        echo "🔐 กำลังติดตั้ง (พิมพ์รหัสผ่านแล้วกด Enter — ตัวอักษรจะไม่แสดงบนจอ)"
        if ! sudo installer -pkg "$PKG" -target /; then
            echo "❌ ติดตั้ง Python ไม่สำเร็จ"
            echo "   ลองติดตั้งเองจาก https://www.python.org/downloads/"
            fail
        fi
        rm -f "$PKG"
        if command -v "$PY_NEW_BIN" &> /dev/null && python_ok "$PY_NEW_BIN"; then
            BASE_PY="$PY_NEW_BIN"
        else
            echo "❌ ติดตั้ง Python เสร็จแล้วแต่หาไม่เจอ — ลองเปิดไฟล์นี้ใหม่อีกครั้ง"
            fail
        fi
        echo "✅ ติดตั้ง Python เรียบร้อย"
        echo ""
    fi

    echo "📦 กำลังสร้าง virtual environment (.venv) — ทำครั้งเดียว..."
    if ! "$BASE_PY" -m venv .venv; then
        echo "❌ สร้าง .venv ไม่สำเร็จ"
        rm -rf .venv
        fail
    fi
    echo ""
fi

source .venv/bin/activate
PYTHON_CMD="python3"
echo "✅ ใช้ virtual environment (.venv): $($PYTHON_CMD --version)"
echo ""

# ── เช็คว่า library ครบหรือยัง ถ้าไม่ครบให้ติดตั้ง ───────────
if ! $PYTHON_CMD -c "import streamlit, pandas, openpyxl, ezdxf, pulp, docx, matplotlib" &> /dev/null; then
    echo "⚠️  ยังไม่มี library ครบ — กำลังติดตั้งให้อัตโนมัติ (ต้องมีอินเทอร์เน็ต อาจใช้เวลาสักครู่)..."
    echo ""
    $PYTHON_CMD -m pip install --upgrade pip &> /dev/null
    if [ -f "requirements.txt" ]; then
        $PYTHON_CMD -m pip install -r requirements.txt
    else
        $PYTHON_CMD -m pip install streamlit pandas openpyxl ezdxf pulp python-docx matplotlib
    fi
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ ติดตั้ง library ไม่สำเร็จ — ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่"
        fail
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
