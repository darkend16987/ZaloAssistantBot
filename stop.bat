@echo off
echo [+] Dang dung he thong Zalo Assistant...

:: Di chuyen den thu muc hien tai cua file .bat
cd /d "%~dp0"

:: Dung va go bo cac container da tao
docker-compose down

echo [+] He thong da duoc dung hoan toan.
pause