@echo off
chcp 65001 >nul
title Gestor ISP
cd /d "%~dp0"
echo ============================================
echo   Gestor ISP - instalacion y arranque
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python no esta instalado o no esta en el PATH.
  echo Instalalo desde https://www.python.org/downloads/
  echo y marca la casilla "Add Python to PATH". Luego vuelve a abrir este archivo.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creando entorno de Python...
  python -m venv .venv || goto fallo
  echo Instalando dependencias, tarda 1-2 minutos...
  .venv\Scripts\python.exe -m pip install -r requirements.txt || goto fallo
)

if not exist .env (
  echo Creando archivo de configuracion .env...
  .venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; import secrets; t=open('.env.example',encoding='utf-8').read(); t=t.replace('FERNET_KEY=','FERNET_KEY='+Fernet.generate_key().decode()).replace('pon-aqui-una-clave-larga-y-secreta',secrets.token_urlsafe(40)); open('.env','w',encoding='utf-8').write(t)" || goto fallo
)

if not exist db.sqlite3 (
  .venv\Scripts\python.exe manage.py migrate || goto fallo
  .venv\Scripts\python.exe manage.py init_roles || goto fallo
  .venv\Scripts\python.exe manage.py seed_demo || goto fallo
) else (
  .venv\Scripts\python.exe manage.py migrate || goto fallo
)

echo.
echo ============================================
echo   Abriendo el panel en el navegador...
echo   Usuario: admin_isp   Contrasena: demo12345
echo   NO CIERRES ESTA VENTANA mientras uses el panel.
echo ============================================
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000/"
.venv\Scripts\python.exe manage.py runserver
pause
exit /b 0

:fallo
echo.
echo [ERROR] Algo fallo. Toma una captura de esta ventana y mandala.
pause
exit /b 1
