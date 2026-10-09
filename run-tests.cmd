@echo off
setlocal
set "MEDIA_FFMPEG_DIR=%~dp0runtime\ffmpeg\bin"
set "HF_HOME=%~dp0runtime\cache\huggingface"
set "HF_XET_CACHE=%~dp0runtime\cache\xet"
set "HF_HUB_OFFLINE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "TEMP=%~dp0runtime\cache\test-temp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
"%~dp0runtime\python\python.exe" -X utf8 -m unittest discover -s "%~dp0tests" -v
exit /b %ERRORLEVEL%
