@echo off
title Xona DBD Dataset Optimizer
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo Python launcher "py" was not found.
    echo Install Python and enable the Python launcher.
    pause
    exit /b 1
)

py -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo Installing Pillow...
    py -m pip install pillow
    if errorlevel 1 (
        echo.
        echo Pillow installation failed.
        echo Run manually: py -m pip install pillow
        pause
        exit /b 1
    )
)

echo.
echo This creates a new Dataset_Optimized folder.
echo Your original Dataset folder will not be modified.
echo.
py "Xona_Dataset_Optimizer.py"

echo.
echo Press any key to close.
pause >nul
