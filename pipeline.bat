@echo off
rem Pipeline completo: arquivos da ANP -^> stage -^> Data Warehouse (ver pipeline.py)
cd /d "%~dp0"
".venv\Scripts\python.exe" pipeline.py %*
set CODIGO=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %CODIGO%
