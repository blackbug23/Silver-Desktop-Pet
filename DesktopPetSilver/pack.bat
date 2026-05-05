@echo off
chcp 65001 >nul
echo ========================================
echo   Silver 桌宠 - 打包为 EXE
echo ========================================
echo.

cd /d "%~dp0"

pyinstaller --noconfirm --onefile --windowed ^
  --name "Silver桌宠" ^
  --icon resources\Silver-1-001.ico ^
  --add-data "resources;resources" ^
  --add-data "desktop_pet;desktop_pet" ^
  main.py

echo.
echo ========================================
echo   打包完成！EXE 在 dist 文件夹中
echo ========================================
pause
