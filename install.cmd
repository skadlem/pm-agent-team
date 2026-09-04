@echo off
rem PMOS template installer (Windows). Usage: install.cmd [host]
rem host: claude (default) | jcode | openhands | hermes
rem Copies the 4 skills from the host's rendered bundle into the host's global
rem skills dir and records the template root (hosts/<host>.json paths).
setlocal enabledelayedexpansion
set "TPL=%~dp0"
set "HOST=%~1"
if "%HOST%"=="" set "HOST=claude"
if not exist "%TPL%hosts\%HOST%.json" (
  echo unknown host "%HOST%"; adapters:
  dir /b "%TPL%hosts\*.json" | findstr /v "\.md$"
  exit /b 2
)
for /f "usebackq delims=" %%A in (`python -c "import json,os,sys; c=json.load(open(sys.argv[1])); print(os.path.expanduser(c['skills_dir'])); print(os.path.expanduser(c['template_root_file']))" "%TPL%hosts\%HOST%.json"`) do (
  if not defined SK (set "SK=%%A") else (set "ROOT=%%A")
)
set "SRC=%TPL%host-bundles\%HOST%\skills"
if not exist "%SRC%" set "SRC=%TPL%skills"
for %%S in (project-team-start project-team-work pm-kb-bootstrap pm-kb-enrich) do (
  if exist "%SK%\%%S" rmdir /s /q "%SK%\%%S"
  xcopy /E /I /Y /Q "%SRC%\%%S" "%SK%\%%S" >nul
)
for %%D in ("%ROOT%") do set "ROOTDIR=%%~dpD"
if not exist "%ROOTDIR%" mkdir "%ROOTDIR%"
> "%ROOT%" echo %TPL%
echo PMOS template installed for host: %HOST%
echo   skills   -^> %SK%
echo   template -^> %ROOT%
if exist "%TPL%host-bundles\%HOST%\README.md" echo   next steps -^> host-bundles\%HOST%\README.md
endlocal
