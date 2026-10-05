@echo off
rem Đóng gói dự án thành file zip để chuyển sang máy khác (bỏ .venv, chrome_profile, logs).
rem File zip nằm ở thư mục QC-Facebook_dong-goi cạnh thư mục dự án.
chcp 65001 >nul
cd /d "%~dp0"
.venv\Scripts\python.exe tools\dong_goi.py
if errorlevel 1 (
    echo ✗ Đóng gói lỗi
    pause
    exit /b 1
)
start "" "%~dp0..\QC-Facebook_dong-goi"
pause
