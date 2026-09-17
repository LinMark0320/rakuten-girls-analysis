@echo off
chcp 65001 >nul
title 樂天女孩卡價監控 - 一鍵更新並發布

echo ======================================================
echo    🚀 樂天女孩卡二級市場行情 - 一鍵自動更新與發布
echo ======================================================
echo.

echo [1/3] 正在執行 Python 爬蟲，掃描 Yahoo 拍賣最新數據...
python run_scanner.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 爬蟲執行失敗，請檢查網路連線或 Python 環境！
    pause
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
    echo ❌ 推送失敗，請檢查 GitHub 連線權限！
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================
echo  🎉 恭喜！最新拍賣數據已全部更新完成！
echo  🌐 線上網頁將在 30~60 秒內自動更新生效：
echo     https://linmark0320.github.io/rakuten-girls-analysis/
echo ======================================================
echo.
pause
