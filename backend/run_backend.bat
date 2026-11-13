@echo off
setlocal enabledelayedexpansion
title AIoT Klasifikasi Udara - Backend Server (Local Venv)

echo =========================================================
echo   AIoT Klasifikasi Kualitas Udara - Backend Server
echo   Mode: Local Virtual Environment (venv)
echo =========================================================
echo.

:: Tentukan direktori backend
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if exist "%SCRIPT_DIR%\src" (
    set "BACKEND_DIR=%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%\backend\src" (
    set "BACKEND_DIR=%SCRIPT_DIR%\backend"
) else (
    set "BACKEND_DIR=%SCRIPT_DIR%"
)

echo [1/3] Menyiapkan direktori...
echo   Backend Directory : %BACKEND_DIR%
echo.

:: 2. Prioritaskan Local Virtual Environment (venv)
echo [2/3] Memeriksa local virtual environment...

set "LOCAL_VENV="

if exist "%BACKEND_DIR%\venv\Scripts\activate.bat" (
    set "LOCAL_VENV=%BACKEND_DIR%\venv"
) else if exist "%SCRIPT_DIR%\..\.venv\Scripts\activate.bat" (
    set "LOCAL_VENV=%SCRIPT_DIR%\..\.venv"
)

if "!LOCAL_VENV!"=="" (
    echo [INFO] Local venv belum ditemukan. Membuat virtual environment baru di backend\venv...
    where python >nul 2>&1
    if !errorlevel! neq 0 (
        echo [ERROR] Python tidak ditemukan di sistem untuk membuat venv!
        pause
        exit /b 1
    )
    python -m venv "%BACKEND_DIR%\venv"
    set "LOCAL_VENV=%BACKEND_DIR%\venv"
    
    echo [INFO] Menginstall dependencies ke local venv...
    call "!LOCAL_VENV!\Scripts\activate.bat"
    python -m pip install --upgrade pip
    pip install -r "%BACKEND_DIR%\requirements.txt"
) else (
    echo   Ditemukan local venv: !LOCAL_VENV!
    call "!LOCAL_VENV!\Scripts\activate.bat"
)

echo   Python aktif:
where python
echo.

:: 3. Jalankan FastAPI Server
echo [3/3] Memulai FastAPI backend server...
echo   Backend URL        : http://localhost:8000
echo   FastAPI Swagger UI : http://localhost:8000/docs
echo   WebSocket Endpoint : ws://localhost:8000/ws/air-quality
echo.
echo Tekan CTRL+C untuk menghentikan server.
echo =========================================================
echo.

cd /d "%BACKEND_DIR%"
set "PYTHONPATH=%BACKEND_DIR%\src;%PYTHONPATH%"

python src\main.py

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Server terhenti dengan kode error: !errorlevel!.
    pause
)
