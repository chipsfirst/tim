@echo off
rem Windows build. Output: dist\TIM\TIM.exe, then installer.iss packs TIM-setup.exe.
rem Name must stay ASCII "TIM": installer.iss and CI reference dist\TIM.
pyinstaller --name "TIM" --windowed --noconfirm --clean --icon icon.ico --add-data "ui;ui" --collect-all pythonnet --hidden-import clr --hidden-import clr_loader --hidden-import webview.platforms.winforms --hidden-import webview.platforms.edgechromium --hidden-import pystray._win32 --hidden-import PIL.Image main.py
