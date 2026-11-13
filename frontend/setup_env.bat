@echo off
cd /d "%~dp0"

echo ========================================================
echo   Frontend Setup (React + Vite)
echo ========================================================
echo.

echo 1. Checking Node.js and npm installation...
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not found!
    echo Please install Node.js from https://nodejs.org/ and try again.
    pause
    exit /b 1
)

where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] npm is not found!
    echo Please ensure npm is installed and added to your PATH.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('node -v') do set NODE_VER=%%v
for /f "tokens=*" %%v in ('npm -v') do set NPM_VER=%%v
echo [OK] Node.js version : %NODE_VER%
echo [OK] npm version     : %NPM_VER%
echo.

echo 2. Installing project dependencies...
echo Running npm install...
call npm install
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install npm dependencies.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   Frontend setup complete!
echo ========================================================
echo.
echo You can run the development server anytime with:
echo   npm run dev
echo or double-click run_dev.bat
echo.

set /p START_NOW="Do you want to start the development server now? (y/n): "
if /i "%START_NOW%"=="y" (
    echo.
    echo Starting development server...
    call npm run dev
)

pause

