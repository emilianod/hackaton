@echo off
echo Subiendo archivo a 0x0.st...
curl -F "file=@subir.zip" https://0x0.st

echo.
echo Eliminando archivo subir.zip...
del subir.zip

echo.
echo Proceso completado.
pause