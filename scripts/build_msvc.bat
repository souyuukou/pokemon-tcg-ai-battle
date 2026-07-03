@echo off
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
cl /nologo /std:c++20 /O2 /GL /arch:AVX2 /W4 /EHsc /LD /Icpp\include cpp\src\engine.cpp /link /LTCG /OUT:sample_submission\pokemon_pvs.dll
if errorlevel 1 exit /b %errorlevel%
copy /Y data\deck_catalog.json sample_submission\deck_catalog.json >nul
