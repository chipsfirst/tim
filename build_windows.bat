@echo off
pyinstaller --name "ТИМ" --onedir --noconfirm --clean --add-data "ui;ui" --hidden-import webview.platforms.edgechromium main.py
