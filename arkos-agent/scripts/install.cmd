@echo off
REM ============================================================================
REM Arkos Installer for Windows (CMD wrapper)
REM ============================================================================
REM This batch file launches the PowerShell installer for users running CMD.
REM
REM Usage:
REM   install.cmd
REM
REM Or if you're already in PowerShell, use the direct command instead:
REM   .\install.ps1
REM ============================================================================

echo.
echo  Arkos Installer
echo  Launching PowerShell installer...
echo.

powershell -ExecutionPolicy ByPass -NoProfile -File "%~dp0install.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  Installation failed. Please try running PowerShell directly:
    echo    powershell -ExecutionPolicy ByPass -File ".\install.ps1"
    echo.
    pause
    exit /b 1
)
