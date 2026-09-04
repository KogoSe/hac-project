@echo off
REM ============================================================
REM run_app.bat — ดับเบิลคลิกเพื่อรัน HAC Load Designer บน Windows
REM วางไฟล์นี้ไว้ที่ hac_project\ (ระดับเดียวกับ app.py)
REM ============================================================

cd /d "%~dp0"

echo ============================================
echo   HAC Load Designer -- เริ่มต้นระบบ
echo ============================================
echo.

REM ── ตรวจสอบว่ามี app.py อยู่จริงไหม ──────────────────────
if not exist "app.py" (
    echo [ERROR] ไม่พบ app.py ในโฟลเดอร์นี้
    echo         ต้องวางไฟล์ run_app.bat นี้ไว้ที่เดียวกับ app.py
    echo.
    pause
    exit /b 1
)

REM ── หา Python ที่จะใช้ ──────────────────────────────────
set PYTHON_CMD=

if exist ".venv\Scripts\python.exe" (
    echo [OK] พบ virtual environment ^(.venv^) -- ใช้ตัวนี้
    call .venv\Scripts\activate.bat
    set PYTHON_CMD=python
) else if exist "venv\Scripts\python.exe" (
    echo [OK] พบ virtual environment ^(venv^) -- ใช้ตัวนี้
    call venv\Scripts\activate.bat
    set PYTHON_CMD=python
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] ไม่พบ Python ในเครื่องเลย
        echo         ต้องติดตั้ง Python 3 ก่อน จาก https://www.python.org/downloads/
        echo         *** ตอนติดตั้งอย่าลืมติ๊ก "Add Python to PATH" ***
        echo.
        pause
        exit /b 1
    )
    echo [OK] ไม่พบ venv -- ใช้ python ของเครื่อง
    set PYTHON_CMD=python
)

echo.
%PYTHON_CMD% --version
echo.

REM ── เช็คว่ามี streamlit ติดตั้งหรือยัง ────────────────────
%PYTHON_CMD% -m streamlit --version >nul 2>nul
if errorlevel 1 (
    echo [!] ยังไม่มี streamlit ในเครื่อง -- กำลังติดตั้งให้อัตโนมัติ...
    echo.
    if exist "requirements.txt" (
        %PYTHON_CMD% -m pip install -r requirements.txt
    ) else (
        %PYTHON_CMD% -m pip install streamlit pandas openpyxl ezdxf
    )
    echo.
)

REM ── รัน Streamlit ────────────────────────────────────────
echo [*] กำลังเปิด HAC Load Designer...
echo     ^(ถ้า browser ไม่เปิดเอง ให้เปิดลิงก์ที่ขึ้นด้านล่างนี้ด้วยตัวเอง^)
echo.
%PYTHON_CMD% -m streamlit run app.py

echo.
echo ============================================
echo   โปรแกรมปิดแล้ว
echo ============================================
pause
