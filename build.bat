@echo off
echo === Git Dummy Build ===
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Clean previous build artifacts
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller with spec file
echo Building executable...
pyinstaller git_dummy.spec --clean

REM Check result
if exist dist\GitDummy.exe (
    echo.
    echo === BUILD SUCCESSFUL ===
    echo Output: dist\GitDummy.exe
    for %%I in (dist\GitDummy.exe) do echo Size: %%~zI bytes
) else (
    echo.
    echo === BUILD FAILED ===
    exit /b 1
)
