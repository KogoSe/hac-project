@echo off
chcp 65001 >nul
setlocal EnableExtensions
REM ============================================================
REM run_app.bat — ดับเบิลคลิกเพื่อรัน HAC Load Designer บน Windows
REM วางไฟล์นี้ไว้ที่ hac_project\ (ระดับเดียวกับ app.py)
REM เครื่องเปล่า: ติดตั้ง Python + library ให้อัตโนมัติ (ต้องมีอินเทอร์เน็ต)
REM ============================================================

set "PY_VERSION=3.12.8"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe"
set "PY_NEW_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

cd /d "%~dp0"

echo ============================================
echo   HAC Load Designer -- เริ่มต้นระบบ
echo ============================================
echo.

REM ── ตรวจสอบว่ามี app.py อยู่จริงไหม ──────────────────────
if not exist "app.py" (
    echo [ERROR] ไม่พบ app.py ในโฟลเดอร์นี้
    echo         ต้องวางไฟล์ run_app.bat นี้ไว้ที่เดียวกับ app.py
    goto :fail
)

REM ── ถ้ามี venv อยู่แล้ว ข้ามไปเช็ค library เลย ────────────
if exist ".venv\Scripts\python.exe" goto :have_venv

REM ── หา Python ของเครื่อง (ต้อง 3.9 ขึ้นไป) ─────────────────
REM   หมายเหตุ: python.exe ใน WindowsApps เป็นแค่ตัวหลอกของ Store
REM   จึงต้องลองรันจริงแทนการใช้ where
set "BASE_PY="
call :try_python py -3
if not defined BASE_PY call :try_python python
if not defined BASE_PY call :try_python "%PY_NEW_EXE%"
if defined BASE_PY goto :make_venv

REM ── ไม่มี Python -> ดาวน์โหลดและติดตั้งให้อัตโนมัติ ───────
echo [!] ไม่พบ Python ในเครื่อง -- กำลังดาวน์โหลดและติดตั้ง Python %PY_VERSION% ให้อัตโนมัติ
echo     ^(ไม่ต้องใช้สิทธิ์ admin / ใช้เวลาประมาณ 1-3 นาที^)
echo.
set "PY_INSTALLER=%TEMP%\python-%PY_VERSION%-installer.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%'"
if errorlevel 1 (
    echo [ERROR] ดาวน์โหลด Python ไม่สำเร็จ -- ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่
    echo         หรือติดตั้งเองจาก https://www.python.org/downloads/
    echo         *** ตอนติดตั้งอย่าลืมติ๊ก "Add Python to PATH" ***
    goto :fail
)
echo [*] กำลังติดตั้ง Python...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_doc=0
del "%PY_INSTALLER%" >nul 2>nul
call :try_python "%PY_NEW_EXE%"
if not defined BASE_PY (
    echo [ERROR] ติดตั้ง Python ไม่สำเร็จ
    echo         ลองติดตั้งเองจาก https://www.python.org/downloads/
    echo         *** ตอนติดตั้งอย่าลืมติ๊ก "Add Python to PATH" ***
    goto :fail
)
echo [OK] ติดตั้ง Python เรียบร้อย
echo.

:make_venv
echo [*] กำลังสร้าง virtual environment ^(.venv^) -- ทำครั้งเดียว...
%BASE_PY% -m venv .venv
if errorlevel 1 (
    echo [ERROR] สร้าง .venv ไม่สำเร็จ
    rmdir /s /q .venv >nul 2>nul
    goto :fail
)
echo.

:have_venv
set "PYTHON_CMD=.venv\Scripts\python.exe"
echo [OK] ใช้ virtual environment ^(.venv^)
%PYTHON_CMD% --version
echo.

REM ── เช็คว่า library ครบหรือยัง ถ้าไม่ครบให้ติดตั้ง ─────────
%PYTHON_CMD% -c "import streamlit, pandas, openpyxl, ezdxf, pulp, docx, matplotlib" >nul 2>nul
if not errorlevel 1 goto :run

echo [!] ยังไม่มี library ครบ -- กำลังติดตั้งให้อัตโนมัติ ^(ต้องมีอินเทอร์เน็ต อาจใช้เวลาสักครู่^)...
echo.
%PYTHON_CMD% -m pip install --upgrade pip >nul 2>nul
if exist "requirements.txt" (
    %PYTHON_CMD% -m pip install -r requirements.txt
) else (
    %PYTHON_CMD% -m pip install streamlit pandas openpyxl ezdxf pulp python-docx matplotlib
)
if errorlevel 1 (
    echo.
    echo [ERROR] ติดตั้ง library ไม่สำเร็จ -- ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่
    goto :fail
)
echo.

:run
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
exit /b 0

:fail
echo.
pause
exit /b 1

REM ── ลองรัน Python ตัวที่ส่งมา ถ้าใช้ได้และเป็น 3.9+ ให้ตั้ง BASE_PY ──
:try_python
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "BASE_PY=%*"
exit /b 0
