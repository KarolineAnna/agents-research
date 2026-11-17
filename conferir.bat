@echo off
REM Confere cada fonte e cada funcao do site com dados reais. O resultado fica em data\conferencia.txt
cd /d "%~dp0"
set PY=
where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py -3
if not defined PY (
  echo Python nao encontrado.
  pause
  exit /b 1
)
%PY% -m pip install -e . -q
%PY% -m indicadores_b3.conferir %*
echo.
echo Pronto. O resultado esta em data\conferencia.txt
pause
