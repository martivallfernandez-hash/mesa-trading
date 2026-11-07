@echo off
setlocal
cd /d "%~dp0"
echo Preparacion del lector de MetaTrader 5 DEMO.
echo Crea un entorno Python local e instala el paquete oficial MetaTrader5.
echo No lee contrasenas ni envia ordenes.
choice /C SN /M "Deseas continuar"
if errorlevel 2 exit /b 0
py -3 -m venv .mt5-env
if errorlevel 1 goto error
.mt5-env\Scripts\python.exe -m pip install -r requirements-windows.txt
if errorlevel 1 goto error
echo Preparacion completada. Abre tu MT5 demo y ejecuta Leer_MT5_Demo.
pause
exit /b 0
:error
echo No se completo la preparacion. Comprueba que Python este instalado en Windows.
pause
exit /b 1
