@echo off
rem Chạy QC-Facebook ở chế độ nền + mở web quản lý.
rem Bấm đúp file này để chạy. Các cửa sổ được thu nhỏ xuống thanh tác vụ:
rem   "QC-Facebook"      : cửa sổ BÌNH LUẬN — bình luận ngay bài mới nhất trong hàng chờ (đóng cửa sổ này để dừng)
rem   "QC-Facebook Quet" và "QC-Facebook Quet 2": 2 cửa sổ QUÉT — chia nhau các nhóm, tìm bài mới cho hàng chờ
rem   "QC-Facebook Web"  : web quản lý http://127.0.0.1:5000
rem Lần đầu chạy song song: đóng các cửa sổ trên rồi chạy  .venv\Scripts\python.exe main.py taophienquet
chcp 65001 >nul
cd /d "%~dp0"
start "QC-Facebook Web" /min cmd /k ".venv\Scripts\python.exe web.py"
start "QC-Facebook" /min cmd /k ".venv\Scripts\python.exe main.py"
if exist "chrome_profile_quet" start "QC-Facebook Quet" /min cmd /k ".venv\Scripts\python.exe main.py quet"
if exist "chrome_profile_quet2" start "QC-Facebook Quet 2" /min cmd /k ".venv\Scripts\python.exe main.py quet 2"
timeout /t 3 >nul
start "" http://127.0.0.1:5000
