@echo off
pyinstaller --name "ТИМ" --onedir --noconfirm --clean --icon icon.ico --add-data "ui;ui" --hidden-import webview.platforms.edgechromium --hidden-import pystray._win32 --hidden-import PIL.Image main.py
