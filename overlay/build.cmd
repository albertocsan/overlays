@echo off
REM Compila la suite completa (Director, servidor overlay, ventana overlay y
REM lanzador) a ejecutables independientes con PyInstaller. No requiere que
REM quien lo ejecute tenga Python instalado - solo hace falta aqui, para compilar.
REM
REM Resultado: carpeta dist\ con 4 subcarpetas (EMS_Overlay, overlay_server,
REM overlay_window, director). Reparte la carpeta dist\ entera; EMS_Overlay.exe
REM es el que se ejecuta para arrancarlo todo.

setlocal
cd /d "%~dp0"

echo [1/4] Compilando Director (controlcamaras.py)...
python -m PyInstaller --noconfirm --windowed --onedir --name director --distpath dist --workpath build_pyi --specpath build_pyi controlcamaras.py
if errorlevel 1 goto :error

echo [2/4] Compilando ventana overlay (renderoverlay.py)...
python -m PyInstaller --noconfirm --windowed --onedir --name overlay_window --distpath dist --workpath build_pyi --specpath build_pyi overlay\renderoverlay.py
if errorlevel 1 goto :error

echo [3/4] Compilando servidor overlay (main.py)...
pushd overlay
python -m PyInstaller --noconfirm --console --onedir --name overlay_server --distpath ..\dist --workpath ..\build_pyi --specpath ..\build_pyi --add-data "%~dp0overlay\web\templates;web/templates" --add-data "%~dp0overlay\web\static;web/static" --paths . main.py
if errorlevel 1 (popd & goto :error)
popd

echo [4/4] Compilando lanzador (overlayWeb.py)...
python -m PyInstaller --noconfirm --console --onedir --name EMS_Overlay --distpath dist --workpath build_pyi --specpath build_pyi overlayWeb.py
if errorlevel 1 goto :error

echo.
echo Listo. Reparte la carpeta dist\ completa (los 4 subcarpetas juntas).
echo Para arrancar: dist\EMS_Overlay\EMS_Overlay.exe
goto :eof

:error
echo.
echo ERROR: la compilacion ha fallado. Revisa el mensaje de arriba.
exit /b 1
