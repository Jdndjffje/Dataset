@echo off
title Xona DBD Dataset Validator
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo Python launcher "py" was not found.
    echo Install Python and make sure the Python launcher is enabled.
    pause
    exit /b 1
)

py -c "import PIL, imagehash" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    py -m pip install pillow imagehash
    if errorlevel 1 (
        echo.
        echo Package installation failed.
        echo Run manually: py -m pip install pillow imagehash
        pause
        exit /b 1
    )
)

py "Xona_Dataset_Validator.py"

echo.
echo Press any key to close.
pause >nul
