@echo off
chcp 65001 >nul
echo ========================================
echo   Silver 桌宠 - 安装依赖
echo ========================================
echo.

pip install PyQt5 openai openpyxl pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo ========================================
echo   安装完成！请运行 run.bat 启动桌宠
echo ========================================
pause
