@echo off
chcp 65001 >nul
title Building Wuwa Tappo Token Extractor - PyInstaller
cd /d "%~dp0"

echo ===================================================
echo   Building GetToken.exe (Desktop Token Extractor)
echo ===================================================

taskkill /F /IM GetToken.exe >nul 2>nul

set "ICON_PATH=%~dp0..\Hsin-Icon.ico"
set "ICON_FLAG="
if exist "%ICON_PATH%" (
    set ICON_FLAG=--icon="%ICON_PATH%"
)

pyinstaller --clean --noconfirm --onefile --console ^
    %ICON_FLAG% ^
    --version-file="version_info.txt" ^
    --name="GetToken" ^
    --distpath="." ^
    get_token.py

if errorlevel 1 (
    echo.
    echo [!] Build failed! Please check errors above.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   Build Complete! GetToken.exe is ready in tool\
echo ===================================================
pause
