@echo off
cd /d "%~dp0"
echo 앱을 시작하는 중... 잠시 후 브라우저가 자동으로 열립니다.
echo (앱 사용 중에는 이 검은 창을 닫지 마세요. 다 쓰면 이 창을 닫으면 됩니다.)
python -m streamlit run app.py
pause
