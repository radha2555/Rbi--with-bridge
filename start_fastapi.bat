:: start_fastapi.bat
@echo off
ECHO Activating virtual environment and starting FastAPI...

:: Change to the directory where this script is located (important for relative paths)
CD /D "%~dp0"

:: Check if the virtual environment directory exists
IF NOT EXIST ".\venv\Scripts\activate.bat" (
    ECHO Error: Virtual environment activation script not found at ".\venv\Scripts\activate.bat"
    ECHO Please check the 'venv' folder name and its contents.
    PAUSE
    EXIT /B 1
)

:: Activate the virtual environment
:: IMPORTANT: Replace 'venv' below if your virtual environment folder has a different name
CALL .\venv\Scripts\activate.bat

IF %ERRORLEVEL% NEQ 0 (
    ECHO Error: Failed to activate virtual environment.
    PAUSE
    EXIT /B 1
)

ECHO Virtual environment activated successfully.

:: Run FastAPI using uvicorn
:: Note: main:app assumes your FastAPI app instance is named 'app' in 'main.py'
uvicorn main:app --host 0.0.0.0 --port 8000

:: The 'deactivate' command should only be executed if uvicorn exits cleanly,
:: but it's usually handled automatically or not strictly necessary in this spawned context
:: as the shell process will close anyway. Removed PAUSE here to allow automatic exit.
:: deactivate