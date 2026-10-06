@echo off
setlocal
cd /d "%~dp0"
title Receitas - Teste
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "COLUMNS=150"
set "LOG=teste-log.txt"
set "VPY=.venv\Scripts\python.exe"

if not exist "%VPY%" goto sem_instalacao
if not exist ".env" goto sem_instalacao

rem ---------- Pasta dos videos: arraste a pasta sobre este .bat ou cole o caminho ----------
set "PASTA=%~1"
if not defined PASTA set /p "PASTA=Cole o caminho da pasta com o video de teste e aperte Enter: "
if not defined PASTA goto pasta_invalida
set "PASTA=%PASTA:"=%"
if "%PASTA:~-1%"=="\" set "PASTA=%PASTA:~0,-1%"
if not exist "%PASTA%\" goto pasta_invalida

echo.
echo ============================================================
echo   FECHE O CAPCUT antes de continuar.
echo   Pasta: %PASTA%
echo   A saida vai ser salva em %LOG%
echo ============================================================
pause

>>"%LOG%" echo.
>>"%LOG%" echo ==================== %date% %time% ====================
>>"%LOG%" echo Pasta: %PASTA%

rem ---------- Rodada 1: sem gastar API e sem gravar no Notion ----------
echo.
echo ===== RODADA 1 de 2: --mock-claude (nao gasta API, nao grava no Notion) =====
>>"%LOG%" echo ===== RODADA 1: --ab-hooks --mock-claude --whisper-model tiny =====
"%VPY%" tools\tee.py "%LOG%" -- "%VPY%" main.py "%PASTA%" --ab-hooks --mock-claude --whisper-model tiny --overwrite --regenerar
if errorlevel 1 goto falha1

rem ---------- Rodada 2: Claude de verdade + grava no Notion ----------
echo.
echo ===== RODADA 2 de 2: Claude real + Notion =====
>>"%LOG%" echo ===== RODADA 2: --ab-hooks --whisper-model tiny =====
"%VPY%" tools\tee.py "%LOG%" -- "%VPY%" main.py "%PASTA%" --ab-hooks --whisper-model tiny --overwrite --regenerar
if errorlevel 1 goto falha2

echo.
echo ============================================================
echo   Teste concluido! Agora:
echo   1. Abra o CapCut: devem aparecer os projetos *_auto_A, _B e _C.
echo   2. Confira a linha da receita no Banco de Receitas do Notion.
echo   3. Me envie o arquivo %LOG% desta pasta.
echo ============================================================
pause
exit /b 0

:falha1
echo.
echo [ERRO] A rodada 1 falhou, entao a rodada 2 nao foi executada - para nao gastar API.
echo   Me envie o arquivo %LOG% desta pasta.
pause
exit /b 1

:falha2
echo.
echo [ERRO] A rodada 2 falhou. Confira se ANTHROPIC_API_KEY e NOTION_TOKEN estao no .env.
echo   Me envie o arquivo %LOG% desta pasta.
pause
exit /b 1

:sem_instalacao
echo [ERRO] Rode primeiro o INSTALAR.bat.
pause
exit /b 1

:pasta_invalida
echo [ERRO] Pasta nao encontrada: %PASTA%
pause
exit /b 1
