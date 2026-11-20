#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m PyInstaller --name "ТИМ" --windowed --noconfirm --clean \
  --add-data "ui:ui" --hidden-import webview.platforms.cocoa \
  --osx-bundle-identifier com.tim.robot main.py
