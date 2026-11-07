@echo off
setlocal
cd /d "%~dp0"
echo Mantiene MT5 abierto y conectado a tu cuenta DEMO.
echo Este lector no abre ni cierra operaciones.
if not exist .mt5-env\Scripts\python.exe goto missing
.mt5-env\Scripts\python.exe mt5_reader.py --output mt5-demo-snapshot.json
if errorlevel 1 goto error
echo Ahora abre el panel privado, Conexion MT5, e importa la lectura generada.
pause
exit /b 0
:missing
echo Primero ejecuta Preparar_MT5_Demo.
pause
exit /b 1
:error
echo La lectura fallo. No se ha activado ninguna operacion. Conserva el mensaje para revisarlo.
pause
exit /b 1
