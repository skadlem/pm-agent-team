@echo off
rem PMOS template installer (Windows). Copies the 3 skills into ~/.jcode/skills
rem and records the template root so skills can find it.
setlocal
set "TPL=%~dp0"
set "SK=%USERPROFILE%\.jcode\skills"
if not exist "%SK%" mkdir "%SK%"
for %%S in (project-team-start project-team-work pm-kb-bootstrap pm-kb-enrich) do (
  xcopy /E /I /Y /Q "%TPL%skills\%%S" "%SK%\%%S" >nul
)
> "%USERPROFILE%\.jcode\pmos-template-root" echo %TPL%
echo PMOS template installed.
echo   skills   -^> %SK%
echo   template -^> %TPL%
endlocal
