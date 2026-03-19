@echo off
title Auto Installer + Python + Modules
cls

echo =======================================
echo  STEP 0: Checking Python...
echo =======================================
echo.

python --version >nul 2>&1
IF %ERRORLEVEL% == 0 (
    echo Python already installed.
    goto install_modules
)

echo Python not found. Installing Python...

curl -o python-installer.exe https://www.python.org/ftp/python/3.12.2/python-3.12.2-amd64.exe

start /wait python-installer.exe /quiet InstallAllUsers=1 PrependPath=1

set "PATH=%PATH%;C:\Program Files\Python312\;C:\Program Files\Python312\Scripts\"

echo.
echo Python installed successfully!
echo.

:install_modules
echo =======================================
echo  STEP 1: Installing Required Modules...
echo =======================================
echo.

python -m pip install --upgrade pip

python -m pip install opencv-python
python -m pip install numpy
python -m pip install mss
python -m pip install pydirectinput
python -m pip install keyboard
python -m pip install PyQt6

echo.
echo =======================================
echo  STEP 2: Starting Script...
echo =======================================
echo.

python "Auto fisher by kaka.py"

echo.
echo ---------------------------------------
echo Program has finished.
pause