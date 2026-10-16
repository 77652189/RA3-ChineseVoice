@echo off
rem 32-bit d3d9.dll proxy for the RA3 test bench (frame capture)
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
cd /d "%~dp0"
cl /nologo /O2 /MT /W3 /LD capture_shim.cpp /Fe:d3d9.dll /link /DEF:exports.def user32.lib kernel32.lib
