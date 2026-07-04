@echo off
cd /d "%~dp0"
echo ========================================
echo   시장 브리핑 모바일 리모컨 서버 시작
echo ========================================
echo 창 2개가 열립니다. 폰으로 쓰는 동안 닫지 마세요.
start "Shorts API :8788" cmd /k "cd /d ""%~dp0"" && python api_server.py"
timeout /t 2 /nobreak >nul
start "Shorts Web :8091" cmd /k "cd /d ""%~dp0mobile-web"" && python -m http.server 8091"
echo.
echo --- 폰 Safari/크롬에서 열 주소 (PC와 같은 Wi-Fi) ---
setlocal EnableDelayedExpansion
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i /c:"IPv4"') do (
    set "ip=%%a"
    set "ip=!ip: =!"
    if not "!ip!"=="" echo   http://!ip!:8091
)
echo 주소가 여러 개면 Wi-Fi에 해당하는 것을 쓰세요.
echo 이 창은 닫아도 됩니다.
pause
