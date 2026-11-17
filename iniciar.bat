@echo off
REM Inicia o site em http://127.0.0.1:8080. Se der erro, o texto fica salvo em iniciar_log.txt.
cd /d "%~dp0"
set PY=
where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py -3
if not defined PY (
  echo Python nao encontrado. Instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
  echo e marque a opcao "Add python.exe to PATH" na instalacao.
  pause
  exit /b 1
)
echo Usando: %PY%
%PY% -m pip install -e . -q > iniciar_log.txt 2>&1
if errorlevel 1 (
  echo A instalacao das bibliotecas falhou. Veja iniciar_log.txt e mande para o Claude.
  type iniciar_log.txt
  pause
  exit /b 1
)
%PY% -m indicadores_b3
echo.
echo O servidor parou. Se apareceu um erro acima, copie e mande para o Claude.
pause
