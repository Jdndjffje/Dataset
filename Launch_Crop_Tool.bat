@echo off
title Xona Dataset Crop Tool
cd /d "%~dp0"

py -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo Pillow is not installed. Installing it now...
    py -m pip install pillow
    if errorlevel 1 (
        echo.
        echo Pillow installation failed.
        echo Run this manually: py -m pip install pillow
        pause
        exit /b 1
    )
)

py "Xona_Dataset_Crop_Tool.py"
if errorlevel 1 pause
