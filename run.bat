@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m podcast_summarizer ingest
.venv\Scripts\python.exe -m podcast_summarizer status
pause
