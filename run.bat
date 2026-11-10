@echo off
setlocal EnableExtensions
title Vilasat AI Support - Launcher

rem ============================================================
rem  Vilasat AI Support Intelligence - one-file launcher
rem
rem  Usage:
rem    run.bat          start everything (live providers when keys exist)
rem    run.bat stop     stop backend, frontend and the local database
rem
rem  No API key? Click "Demo" in the app header. Demo mode uses the
rem  deterministic local retrieval/generation over the same stored help
rem  articles, never touches saved keys or the live index, and is refused
rem  when ENVIRONMENT=production.
rem
rem  What it does (start):
rem    1. checks / installs prerequisites (backend venv, node_modules)
rem    2. starts the bundled PostgreSQL + pgvector cluster
rem    3. applies Alembic migrations
rem    4. indexes the knowledge corpus (incremental, idempotent)
rem    5. starts the FastAPI backend (port 8000) in its own window
rem    6. starts the Next.js frontend (port 3000) in its own window
rem    7. waits for /health, then warms up the pages (first dev compile),
rem       then opens the browser on a ready screen
rem ============================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "PY=%BACKEND%\.venv\Scripts\python.exe"

if /i "%~1"=="stop" goto :stop
if "%~1"==""        goto :check_venv

echo Unknown option: %~1
echo Usage: run.bat [stop]
goto :fail

rem ----------------------------------------------------------
rem  0. Kill previous instances (ports 8000 + 3000-3005)
rem     Guarantees a single clean instance: no port conflicts,
rem     no two dev servers sharing one .next (asset 404s).
rem ----------------------------------------------------------
:kill_ports
for %%p in (8000 3000 3001 3002 3003 3004 3005) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr /R /C:":%%p .*LISTENING"') do taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul
goto :eof

rem ----------------------------------------------------------
rem  1. Prerequisites (previous instances are killed first)
rem ----------------------------------------------------------
:check_venv
echo [0/6] Stopping previous instances (ports 8000, 3000-3005)...
call :kill_ports
echo [1/6] Checking prerequisites...

if exist "%PY%" goto :check_node

echo     backend venv not found - creating it (one-time, needs Python 3.12)...
where python >nul 2>&1 || (echo ERROR: Python not found on PATH. Install Python 3.12 first. & goto :fail)
pushd "%BACKEND%"
python -m venv .venv || (popd & goto :fail)
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (popd & goto :fail)
popd

:check_node
if exist "%ROOT%node_modules" goto :prereq_ok

echo     node_modules not found - installing (one-time, needs Node.js)...
where npm >nul 2>&1 || (echo ERROR: npm not found on PATH. Install Node.js first. & goto :fail)
pushd "%ROOT%"
call npm install || (popd & goto :fail)
popd

:prereq_ok
echo     prerequisites OK.

rem ----------------------------------------------------------
rem  2. Database
rem ----------------------------------------------------------
echo [2/6] Starting local PostgreSQL + pgvector cluster...
pushd "%BACKEND%"
"%PY%" scripts\dev_db.py start || (popd & goto :fail)

echo [3/6] Applying database migrations...
"%PY%" -m alembic upgrade head || (popd & goto :fail)
popd

rem ----------------------------------------------------------
rem  3. Provider configuration (real NVIDIA providers only)
rem ----------------------------------------------------------
echo [4/6] Mode: REAL PROVIDERS (NVIDIA embeddings + chat model)
if not exist "%BACKEND%\.env" (
    echo     WARNING: backend\.env not found - add EMBEDDING_API_KEY and
    echo     NVIDIA_API_KEY there, otherwise chat turns return 503.
)

echo     Indexing knowledge corpus (incremental; skipped chunks cost nothing)...
pushd "%BACKEND%"
"%PY%" scripts\index_knowledge.py
if errorlevel 1 (
    popd
    echo     WARNING: indexing failed - check EMBEDDING_API_KEY. Chat will
    echo     return 503 until the corpus is indexed.
) else (
    popd
)

rem ----------------------------------------------------------
rem  4. Start servers in their own windows
rem ----------------------------------------------------------
echo [5/6] Starting backend on http://127.0.0.1:8000 ...
start "Vilasat Backend" /D "%BACKEND%" cmd /k ""%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [6/6] Starting frontend on http://localhost:3000 ...
start "Vilasat Frontend" /D "%ROOT%" cmd /k "npm run dev"

rem ----------------------------------------------------------
rem  5. Wait for backend health, then open the browser
rem ----------------------------------------------------------
set /a TRIES=0
:waitloop
curl -sf http://127.0.0.1:8000/health >nul 2>&1 && goto :ready
set /a TRIES+=1
if %TRIES% geq 45 goto :nohealth
timeout /t 1 /nobreak >nul
goto :waitloop

:ready
echo.
echo     Backend is healthy.
echo     Warming up the frontend (first compile takes a few seconds)...
node "%ROOT%scripts\prewarm.mjs" http://localhost:3000 / /staff
start "" http://localhost:3000
goto :summary

:nohealth
echo.
echo     NOTE: backend did not report healthy within 45s.
echo     Check the "Vilasat Backend" window for errors.

:summary
echo.
echo ============================================================
echo  Vilasat AI Support is starting
echo    Customer chat : http://localhost:3000
echo    Staff queue   : http://localhost:3000/staff
echo    API docs      : http://127.0.0.1:8000/docs
echo.
echo  Two windows opened: "Vilasat Backend" and "Vilasat Frontend".
echo  Close them to stop the servers, or run:  run.bat stop
echo.
echo  No API key? Click "Demo" in the app header (no network, no key).
echo ============================================================
pause
exit /b 0

rem ----------------------------------------------------------
rem  stop mode
rem ----------------------------------------------------------
:stop
echo Stopping Vilasat AI Support...
call :kill_ports
if exist "%PY%" (
    pushd "%BACKEND%"
    "%PY%" scripts\dev_db.py stop
    popd
)
echo Stopped. (The launcher windows may need a manual close.)
pause
exit /b 0

rem ----------------------------------------------------------
rem  failure exit
rem ----------------------------------------------------------
:fail
echo.
echo *** Launcher failed - read the messages above. ***
pause
exit /b 1
