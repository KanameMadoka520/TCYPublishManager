@echo off
chcp 65001 >nul
echo ================================================
echo   TCY Publish Manager - 一键构建
echo ================================================
echo.

python build.py

echo.
pause
