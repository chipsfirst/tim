"""macOS-реализация платформенного слоя: экран, курсор, трей, хоткей, автозапуск.

Всё, что раньше жило в ветках `if sys.platform == "darwin"` внутри Bot.
"""

import os
import sys
import threading
import time

PLIST = "~/Library/LaunchAgents/com.tim.robot.plist"
OWNS_DRAG = False   # перетаскивание ведёт Bot.track()


def call_soon(fn):
    from PyObjCTools import AppHelper

    AppHelper.callAfter(fn)


def setup():
    """На macOS готовая система координат, отдельной настройки не нужно."""
    return None


def work_area():
    try:
        from AppKit import NSScreen

        screen = NSScreen.mainScreen().frame()
        frame = NSScreen.mainScreen().visibleFrame()
        top = screen.size.height - (frame.origin.y + frame.size.height)
        return (int(frame.origin.x), int(top),
                int(frame.size.width), int(frame.size.height))
    except Exception:
        return None


def cursor():
    try:
        from AppKit import NSEvent, NSScreen

        point = NSEvent.mouseLocation()
        height = NSScreen.mainScreen().frame().size.height
        down = NSEvent.pressedMouseButtons() > 0
        return (float(point.x), float(height - point.y)), down
    except Exception:
        return None, False


def move_window(win, x, y):
    win.move(int(x), int(y))


def set_click_through(win, ignore):
    """Прозрачность для мыши: вне робота клики уходят на рабочий стол."""
    try:
        native = getattr(win, "native", None)
        if native is None or not hasattr(native, "setIgnoresMouseEvents_"):
            return
        from PyObjCTools import AppHelper

        AppHelper.callAfter(native.setIgnoresMouseEvents_, bool(ignore))
    except Exception as exc:
        _log("click-through: %r" % exc)


def start_drag(bot):
    """Перетаскивание на macOS ведёт общий цикл Bot.track()."""
    return None


def start_tray(bot):
    try:
        from AppKit import (NSStatusBar, NSMenu, NSMenuItem,
                            NSVariableStatusItemLength)
        from Foundation import NSObject
        from PyObjCTools import AppHelper
    except Exception as exc:
        _log("tray import failed: %r" % exc)
        return

    class TrayTarget(NSObject):
        def show_(self, sender):
            bot.focus_input()

        def sound_(self, sender):
            bot.toggle_sound_js()

        def quit_(self, sender):
            os._exit(0)

    def build():
        try:
            item = NSStatusBar.systemStatusBar().statusItemWithLength_(
                NSVariableStatusItemLength)
            item.button().setTitle_("Т")
            menu = NSMenu.alloc().init()
            target = TrayTarget.alloc().init()
            for title, sel in (("Показать", b"show:"), ("Звук", b"sound:"),
                               ("Выход", b"quit:")):
                mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
                mi.setTarget_(target)
                menu.addItem_(mi)
            item.setMenu_(menu)
            bot.tray_target = target
            bot.tray_item = item
            _log("native tray ok")
        except Exception as exc:
            _log("tray build failed: %r" % exc)

    AppHelper.callAfter(build)
    threading.Thread(target=lambda: start_hotkey(bot), daemon=True).start()


def start_hotkey(bot):
    try:
        import Quartz
    except Exception as exc:
        _log("hotkey import failed: %r" % exc)
        return

    def handler(proxy, etype, event, refcon):
        try:
            if etype == Quartz.kCGEventTapDisabledByTimeout:
                Quartz.CGEventTapEnable(bot.tap, True)
                return event
            flags = Quartz.CGEventGetFlags(event)
            code = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode)
            if code == 49 and (flags & Quartz.kCGEventFlagMaskAlternate):
                bot.focus_input()
                return None
        except Exception as exc:
            _log("hotkey handler: %r" % exc)
        return event

    try:
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault, mask, handler, None)
        if not tap:
            _log("hotkey tap failed: нужен доступ «Универсальный доступ»")
            return
        bot.tap = tap
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        _log("hotkey ok (alt+space)")
        Quartz.CFRunLoopRun()
    except Exception as exc:
        _log("hotkey failed: %r" % exc)


def install_autostart():
    if not getattr(sys, "frozen", False):
        return False
    try:
        path = os.path.expanduser(PLIST)
        if os.path.exists(path):
            return True
        os.makedirs(os.path.dirname(path), exist_ok=True)
        exe = os.path.abspath(sys.executable)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict>'
                '<key>Label</key><string>com.tim.robot</string>'
                '<key>ProgramArguments</key><array><string>%s</string></array>'
                '<key>RunAtLoad</key><true/>'
                '</dict></plist>\n' % exe
            )
        return True
    except Exception as exc:
        _log("autostart failed: %r" % exc)
        return False


def _log(msg, level="info"):
    """Лог приходит из main, чтобы не заводить второй файл."""
    try:
        from main import log

        log(msg, level)
    except Exception:
        pass
