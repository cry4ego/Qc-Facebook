@echo off
rem Cài đặt trên MÁY MỚI sau khi giải nén: kiểm tra Python + Chrome, tạo .venv, cài thư viện, đăng nhập Facebook.
rem Chạy 1 lần. Sau đó bấm đúp chay-ngam.bat để chạy.
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] Kiểm tra Python...
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo ✗ Chưa có Python 3.10 trở lên. Cài Python 3.13 tại trang vừa mở, NHỚ TICK "Add python.exe to PATH",
    echo   rồi chạy lại file này.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [2/4] Kiểm tra Google Chrome...
set CHROME=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME=1
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME=1
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set CHROME=1
if not defined CHROME (
    echo ✗ Chưa cài Google Chrome. Cài tại trang vừa mở rồi chạy lại file này.
    start "" https://www.google.com/chrome/
    pause
    exit /b 1
)

echo [3/4] Tạo môi trường .venv và cài thư viện (vài phút)...
if not exist ".venv\Scripts\python.exe" python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip >nul
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo ✗ Cài thư viện lỗi - kiểm tra mạng rồi chạy lại.
    pause
    exit /b 1
)

echo [4/4] Đăng nhập Facebook: Chrome sẽ mở ra, đăng nhập (xác minh nếu Facebook hỏi), xong quay lại đây nhấn Enter.
.venv\Scripts\python.exe main.py login

echo.
echo ✓ Cài đặt xong. Bấm đúp chay-ngam.bat để chạy, web quản lý: http://127.0.0.1:5000
echo   (Nhớ TẮT script ở máy cũ - không chạy 2 máy cùng 1 tài khoản Facebook.)
pause
