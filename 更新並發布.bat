@echo off
chcp 65001 >nul
title 樂天女孩卡價監控 - 一鍵更新並發布
cd /d "%~dp0"

set "IS_SCHEDULED=0"
if /I "%~1"=="/scheduled" set "IS_SCHEDULED=1"

if "%IS_SCHEDULED%"=="1" (
    call :main >> "%~dp0update_log.txt" 2>&1
) else (
    call :main
)
exit /b %ERRORLEVEL%

:main
echo ======================================================
echo    %date% %time%
echo    樂天女孩卡二級市場行情 - 一鍵自動更新與發布
echo ======================================================
echo.

echo [1/3] 正在執行 Python 爬蟲，掃描 Yahoo 拍賣最新數據...
python run_scanner.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [失敗] 爬蟲執行失敗，請檢查網路連線或 Python 環境！
    if "%IS_SCHEDULED%"=="0" pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] 正在將最新數據打包並提交到 Git...
git add data/ cards.db
git commit -m "update: 自動更新拍賣卡片數據 (%date% %time%)"

echo.
echo [3/3] 正在推送到 GitHub，同步線上公開網頁...
git push origin main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [失敗] 推送失敗，請檢查 GitHub 連線權限！
    if "%IS_SCHEDULED%"=="0" pause
    exit /b %ERRORLEVEL%
)

echo.
python crawler\print_success_banner.py
echo.
if "%IS_SCHEDULED%"=="0" pause
exit /b 0
