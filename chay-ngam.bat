@echo off
rem Chạy QC-Facebook ở chế độ nền + mở web quản lý.
rem Bấm đúp file này để chạy. Hai cửa sổ được thu nhỏ xuống thanh tác vụ:
rem   "QC-Facebook"      : script quét nhóm & bình luận  (đóng cửa sổ này để dừng script)
rem   "QC-Facebook Web"  : web quản lý http://127.0.0.1:5000
chcp 65001 >nul
cd /d "%~dp0"
start "QC-Facebook Web" /min cmd /k ".venv\Scripts\python.exe web.py"
start "QC-Facebook" /min cmd /k ".venv\Scripts\python.exe main.py"
timeout /t 3 >nul
start "" http://127.0.0.1:5000
