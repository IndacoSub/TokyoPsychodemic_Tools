@echo off
setlocal

REM Controllo che sia stato passato un file
if "%~1"=="" (
    echo Trascina un file .txt sopra questo script.
    pause
    exit /b
)

REM File trascinato
set "INPUT=%~1"

REM Cartella del .bat
set "BATDIR=%~dp0"

REM Cartella precedente (dove sta clean_font_monobehavior.py)
set "PYDIR=%BATDIR%.."

REM Output temporaneo nella cartella del .bat
set "OUTPUT=%BATDIR%cleaned_tmp.txt"

REM Cancella output se esiste
if exist "%OUTPUT%" del /q "%OUTPUT%"

REM Esegui il programma Python dalla cartella precedente
python "%PYDIR%\clean_font_monobehavior.py" "%INPUT%" "%OUTPUT%"

echo Operazione completata.
echo File pulito: %OUTPUT%
pause
endlocal
