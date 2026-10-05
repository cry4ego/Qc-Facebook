@echo off
rem Chỉ mở web quản lý (không chạy script bình luận). Đóng cửa sổ "QC-Facebook Web" để tắt.
chcp 65001 >nul
cd /d "%~dp0"
start "QC-Facebook Web" /min cmd /k ".venv\Scripts\python.exe web.py"
timeout /t 3 >nul
start "" http://127.0.0.1:5000
