@echo off
setlocal enabledelayedexpansion

REM Definisci l'array delle lingue
set LANGUAGES=English JapaneseEmpty Korean SimplifiedChinese TraditionalChinese

REM Loop sulle lingue
for %%L in (%LANGUAGES%) do (
    echo --- Elaborazione di %%L ---

    REM Cancella il dump se esiste
    if exist "%%L_Dump.txt" del /q "%%L_Dump.txt"

    REM Esegui il plugin per generare il dump
    python "plugin_to_export_dump.py" "%%L.txt" "%%L_Dump.txt"

    REM Controllo errore
    if not exist "%%L_Dump.txt" (
        echo ERRORE: %%L_Dump.txt non e' stato creato.
        pause
        exit /b 1
    )
)

REM Esegui lo script finale
python "script.py"

endlocal
