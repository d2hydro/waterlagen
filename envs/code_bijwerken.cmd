@echo off
setlocal
rem Het hele blok wordt ingelezen voordat de updater dit bestand kan vervangen.
(
    pixi exec --spec "python=3.13" -- python "%~dp0code_bijwerken.py" %*
    if errorlevel 1 (
        echo Bijwerken is niet geslaagd. Lees de melding hierboven.
        if "%~1"=="" pause
        exit /b 1
    )
    if "%~1"=="" pause
    exit /b 0
)
