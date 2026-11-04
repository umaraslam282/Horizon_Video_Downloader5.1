@echo off
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process cmd.exe -Verb RunAs -ArgumentList '/c %~s0' -Wait"
    exit /b
)
findstr /i "hvd.com" "%WINDIR%\System32\drivers\etc\hosts" >nul
if %errorLevel% neq 0 (
    echo.>> "%WINDIR%\System32\drivers\etc\hosts"
    echo 127.0.0.1 hvd.com>> "%WINDIR%\System32\drivers\etc\hosts"
    echo 127.0.0.1 www.hvd.com>> "%WINDIR%\System32\drivers\etc\hosts"
    ipconfig /flushdns >nul
    echo [OK] Domain hvd.com mapped to 127.0.0.1
) else (
    echo [OK] Already mapped
)
