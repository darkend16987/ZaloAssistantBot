@echo off
echo [+] Khoi dong he thong Zalo Assistant...

:: Di chuyen den thu muc hien tai cua file .bat
cd /d "%~dp0"

:: Chay Docker Compose de xay dung (neu can) va khoi dong cac container
docker-compose up --build

echo [+] He thong da dung.
pause