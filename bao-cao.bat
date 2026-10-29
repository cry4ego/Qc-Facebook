@echo off
rem Báo cáo sáng của công ty AI: tính bằng code từ dữ liệu của bot (không tốn tiền, không gọi AI), in ra màn hình và lưu
rem vào data\bao_cao\<ngày>.md. Xem đẹp hơn ở tab "Công ty AI" trên web.
chcp 65001 >nul
cd /d "%~dp0"
.venv\Scripts\python.exe main.py baocao
pause
