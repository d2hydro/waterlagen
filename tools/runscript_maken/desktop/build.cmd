@echo off
setlocal
pushd "%~dp0" || exit /b 1
rem Microsoft.Web.WebView2 1.0.3719.77 from NuGet, net462 + win-x64 loader.
"%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /codepage:65001 /target:winexe /win32manifest:Runmaker.manifest /platform:x64 /win32icon:..\web\waterlagen.ico /out:Waterlagen.Runmaker.exe /reference:System.Windows.Forms.dll,System.Drawing.dll,Microsoft.Web.WebView2.Core.dll,Microsoft.Web.WebView2.WinForms.dll Runmaker.cs
exit /b %errorlevel%
