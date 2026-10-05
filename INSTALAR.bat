@echo off
setlocal
cd /d "%~dp0"
title Receitas - Instalacao
echo ============================================================
echo   Receitas Praticas - Instalacao
echo ============================================================
echo.

rem ---------- 1. Python 3.11 ou mais novo ----------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto sem_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto python_velho
for /f "delims=" %%v in ('%PY% --version') do echo [OK] %%v encontrado

rem ---------- 2. FFmpeg ----------
where ffmpeg >nul 2>&1 || goto sem_ffmpeg
where ffprobe >nul 2>&1 || goto sem_ffmpeg
echo [OK] FFmpeg encontrado

rem ---------- 3. Ambiente virtual + dependencias ----------
if exist ".venv\Scripts\python.exe" goto venv_ok
echo.
echo Criando o ambiente virtual em .venv ...
%PY% -m venv .venv
if errorlevel 1 goto erro_venv
:venv_ok
echo.
echo Instalando as dependencias - pode levar alguns minutos ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro_pip
".venv\Scripts\python.exe" -c "import faster_whisper, pycapcut, anthropic, rich, dotenv, requests"
if errorlevel 1 goto erro_pip
echo [OK] Dependencias instaladas

rem ---------- 4. Arquivo .env ----------
if exist ".env" goto env_existe
copy ".env.exemplo" ".env" >nul
echo [OK] Arquivo .env criado
goto abrir_env
:env_existe
echo [OK] Arquivo .env ja existe - mantido como esta
:abrir_env
echo.
echo ============================================================
echo   Instalacao concluida!
echo.
echo   Agora o Bloco de Notas vai abrir o arquivo .env.
echo   Preencha ANTHROPIC_API_KEY= e NOTION_TOKEN= com suas chaves,
echo   salve com Ctrl+S e feche. Depois rode o TESTAR.bat.
echo ============================================================
pause
start "" notepad ".env"
exit /b 0

:sem_python
echo [FALTA] Python nao encontrado.
echo.
echo   Instale o Python 3.12 por UM destes caminhos:
echo   a) No PowerShell:  winget install Python.Python.3.12
echo   b) Ou baixe em https://www.python.org/downloads/
echo      e MARQUE a opcao "Add python.exe to PATH" na instalacao.
echo.
echo   Depois feche esta janela e rode o INSTALAR.bat de novo.
pause
exit /b 1

:python_velho
echo [FALTA] Seu Python e antigo. Precisa da versao 3.11 ou mais nova.
%PY% --version
echo.
echo   Instale o Python 3.12:  winget install Python.Python.3.12
echo   ou em https://www.python.org/downloads/
echo   Depois feche esta janela e rode o INSTALAR.bat de novo.
pause
exit /b 1

:sem_ffmpeg
echo [FALTA] FFmpeg nao encontrado.
echo.
echo   No PowerShell, rode:  winget install Gyan.FFmpeg
echo   Depois FECHE e abra de novo esta janela e rode o INSTALAR.bat outra vez.
pause
exit /b 1

:erro_venv
echo [ERRO] Nao consegui criar o ambiente virtual .venv.
echo   Tire o projeto do OneDrive/Desktop e coloque em C:\Receitas, depois tente de novo.
pause
exit /b 1

:erro_pip
echo [ERRO] Falha ao instalar as dependencias. Veja a mensagem acima.
echo   Dicas: confira a internet; se citar "Microsoft Visual C++", instale o
echo   "Visual C++ Redistributable" em https://aka.ms/vs/17/release/vc_redist.x64.exe
pause
exit /b 1
