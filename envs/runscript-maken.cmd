@echo off
setlocal
pushd "%~dp0"
if not exist pixi.toml cd ..
pixi run --locked python "%~dp0runscript_maken.py"
if errorlevel 1 pause
popd
