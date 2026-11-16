@echo off
rem Barrens Voice: starts WoW through Battle.net, reads chat lines from the addon's strip and speaks them.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Creating the Python environment...
    python -m venv .venv || goto :fail
)
rem (re)install when requirements.txt differs from the one installed last (a new version of the program)
fc /b requirements.txt .venv\requirements.txt >nul 2>&1 && goto :run
echo Installing the libraries...
.venv\Scripts\python.exe -m pip install -q -r requirements.txt || goto :fail
rem RUAccent pulls in the CPU-only onnxruntime; the race voices want the video card's build of it: CUDA on
rem NVIDIA (the game keeps running smoothly; ~1.9 GB more), DirectML on other DirectX 12 cards
.venv\Scripts\python.exe -m pip uninstall -q -y onnxruntime onnxruntime-gpu onnxruntime-directml
where nvidia-smi >nul 2>&1 && (
    echo NVIDIA found: ONNX Runtime with CUDA...
    .venv\Scripts\python.exe -m pip install -q "onnxruntime-gpu[cuda,cudnn]==1.32.0" || goto :fail
) || (
    .venv\Scripts\python.exe -m pip install -q --force-reinstall --no-deps onnxruntime-directml==1.24.4 || goto :fail
)
copy /y requirements.txt .venv\requirements.txt >nul
:run
title Barrens Voice
.venv\Scripts\python.exe -m bv %*
if errorlevel 1 pause
exit /b
:fail
echo Setup failed.
pause
