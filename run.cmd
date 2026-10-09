@echo off
setlocal
set "HF_HOME=%~dp0runtime\cache\huggingface"
set "HF_XET_CACHE=%~dp0runtime\cache\xet"
set "HF_HUB_OFFLINE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%~dp0runtime\python\python.exe" -X utf8 "%~dp0douyin-media\scripts\media_workflow.py" %*
exit /b %ERRORLEVEL%
