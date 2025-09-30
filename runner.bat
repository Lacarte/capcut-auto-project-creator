@echo on
pushd %~dp0

:: Check if venv exists
IF EXIST .venv (
    :: Run your script using this venv's python.exe
    .\.venv\Scripts\python.exe main.py
) ELSE (
    :: Run your script using the system's python
    python main.py
)

pause
