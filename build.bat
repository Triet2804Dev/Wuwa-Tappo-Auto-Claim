@echo off
chcp 65001 >nul
title Building Wuwa Tappo Auto Claim - PyInstaller
cd /d "%~dp0"

echo ===================================================
echo   Building WuwaTappoAutoClaim.exe (All-In-One)
echo ===================================================

taskkill /F /IM WuwaTappoAutoClaim.exe >nul 2>nul
echo [1/3] Generating icon if missing...
python -c "from PIL import Image; img=Image.open('Hsin-Icon.png'); img.save('Hsin-Icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

echo [2/3] Compiling standalone executable with PyInstaller...
pyinstaller --clean --noconfirm --onefile --console ^
    --icon="Hsin-Icon.ico" ^
    --add-data="Hsin-Icon.png;." ^
    --add-data="Hsin-Icon.ico;." ^
    --collect-data certifi ^
    --version-file="version_info.txt" ^
    --name="WuwaTappoAutoClaim" ^
    auto_claim.py

if errorlevel 1 (
    echo.
    echo [!] Build failed! Please check errors above.
    pause
    exit /b 1
)

echo.
echo [3/3] Copying executable to workspace root...
if exist "dist\WuwaTappoAutoClaim.exe" (
    copy /y "dist\WuwaTappoAutoClaim.exe" "WuwaTappoAutoClaim.exe" >nul
    echo [+] Success: WuwaTappoAutoClaim.exe is ready!
)

echo ===================================================
echo   Build Complete!
echo ===================================================
pause

