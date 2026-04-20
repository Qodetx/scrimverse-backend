@echo off
cd /d "c:\Users\Kishan B M\scrimverse-backend"
echo Starting Django server (no reload)...
venv\Scripts\python.exe manage.py runserver 8000 --noreload
pause
