#!/usr/bin/env python3
"""Т.И.М. — техническая иммерсивная модель в углу экрана.

Стоит на месте, живёт глазами, попискивает как R2-D2 и умеет спрашивать
Алису через браузерное окно. Кот Поля живёт отдельно и это не затрагивает.
"""

import json
import os
import sys
import threading
import time

import webview

APP_DIR = os.path.dirname(os.path.abspath(__file__))

WIN_W, WIN_H = 320, 420
ALICE_URL = "https://alice.yandex.ru/"

if sys.platform == "win32":
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
else:
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BLOCKED_JS = "(document.body && document.body.innerText || '').slice(0, 600)"

READ_JS = """
(function () {
  var nodes = document.querySelectorAll('[class*="message"], [class*="Message"], [data-testid*="message"], [class*="reply"], [class*="answer"]');
  for (var i = nodes.length - 1; i >= 0; i--) {
    var t = (nodes[i].innerText || "").replace(/\\s+/g, " ").trim();
    if (t.length >= 12) return t.slice(0, 900);
  }
  return "";
})()
"""

SUBMIT_JS = """
(function (text) {
  var nodes = document.querySelectorAll('textarea, input[type="text"], [contenteditable="true"], [role="textbox"]');
  if (!nodes.length) return "no-input";
  var el = nodes[nodes.length - 1];
  el.focus();
  if (el.isContentEditable) {
    el.textContent = text;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
  } else {
    var proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, text);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
  return "sent";
})(%s)
"""


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None)
    candidates = []
    if base:
        candidates.append(os.path.join(base, rel))
    candidates.append(os.path.join(APP_DIR, rel))
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "..", "Resources", rel))
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)
    return os.path.abspath(candidates[-1])


def log(msg):
    try:
        if sys.platform == "darwin":
            base = os.path.join(os.path.expanduser("~"), "Library", "Logs")
        else:
            base = os.environ.get("TEMP") or os.path.expanduser("~")
        with open(os.path.join(base, "TIM.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


class Api:
    def __init__(self, bot):
        self.bot = bot

    def ready(self):
        self.bot.on_ready()

    def set_regions(self, robot, panel):
        self.bot.set_regions(robot, panel)

    def set_panel(self, is_open):
        self.bot.panel_open = bool(is_open)
        self.bot.ignore_state = None

    def ask(self, text):
        log("ask from ui: %r" % (text or "")[:40])
        return self.bot.ask_alice(text)

    def login(self):
        log("login pressed")
        return "opened" if self.bot.show_alice() else "failed"

    def quit(self):
        self.bot.quit()


class Bot:
    def __init__(self):
        self.win = None
        self.ready = False
        self.placed = False
        self.stop_flag = False

        self.regions = {"robot": None, "panel": None}
        self.hover = False
        self.panel_open = False
        self.menu_open = False
        self.ignore_state = None

        self.x = 0.0
        self.y = 0.0

        self.alice = None
        self.alice_lock = threading.Lock()
        self.btn_sound = True

        self.dragging = False
        self.drag_off = (0.0, 0.0)
        self.last_activity = time.time()
        self.sleeping = False

    # -------------------------------------------------- окно

    def work_area(self):
        try:
            if sys.platform == "darwin":
                from AppKit import NSScreen

                screen = NSScreen.mainScreen().frame()
                frame = NSScreen.mainScreen().visibleFrame()
                top = screen.size.height - (frame.origin.y + frame.size.height)
                return int(frame.origin.x), int(top), int(frame.size.width), int(frame.size.height)
            if sys.platform == "win32":
                import ctypes
                from ctypes import wintypes

                rect = wintypes.RECT()
                ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass
        screen = webview.screens[0]
        return screen.x, screen.y, screen.width, screen.height

    def setup_position(self):
        wx, wy, ww, wh = self.work_area()
        self.x = float(wx + ww - WIN_W - 12)
        self.y = float(wy + wh - WIN_H - 2)

    def place(self):
        if self.placed or self.win is None:
            return
        try:
            self.win.move(int(self.x), int(self.y))
            self.placed = True
        except Exception:
            pass

    def on_ready(self):
        self.ready = True
        self.place()
        threading.Thread(target=self.start_tray, daemon=True).start()

    def focus_input(self):
        try:
            self.win.evaluate_js("document.getElementById('q').focus()")
        except Exception:
            pass

    def toggle_sound_js(self):
        try:
            self.win.evaluate_js(
                "document.getElementById('sound')"
                ".dispatchEvent(new MouseEvent('click',{bubbles:true}))")
        except Exception:
            pass

    def start_tray(self):
        if sys.platform != "darwin":
            return
        try:
            from AppKit import (NSStatusBar, NSMenu, NSMenuItem,
                                NSVariableStatusItemLength)
            from Foundation import NSObject
            from PyObjCTools import AppHelper
        except Exception as exc:
            log("tray import failed: %r" % exc)
            return

        bot = self

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
                self.tray_target = target
                self.tray_item = item
                log("native tray ok")
            except Exception as exc:
                log("tray build failed: %r" % exc)

        AppHelper.callAfter(build)
        threading.Thread(target=self.start_hotkey, daemon=True).start()

    def start_hotkey(self):
        if sys.platform != "darwin":
            return
        try:
            import Quartz
        except Exception as exc:
            log("hotkey import failed: %r" % exc)
            return

        def handler(proxy, etype, event, refcon):
            try:
                if etype == Quartz.kCGEventTapDisabledByTimeout:
                    Quartz.CGEventTapEnable(self.tap, True)
                    return event
                flags = Quartz.CGEventGetFlags(event)
                code = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode)
                if code == 49 and (flags & Quartz.kCGEventFlagMaskAlternate):
                    self.focus_input()
                    return None
            except Exception as exc:
                log("hotkey handler: %r" % exc)
            return event

        try:
            mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault, mask, handler, None)
            if not tap:
                log("hotkey tap failed: нужен доступ «Универсальный доступ»")
                return
            self.tap = tap
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
            log("hotkey ok (alt+space)")
            Quartz.CFRunLoopRun()
        except Exception as exc:
            log("hotkey failed: %r" % exc)

    def quit(self):
        log("quit requested")
        os._exit(0)

    # -------------------------------------------------- мышь

    def cursor(self):
        try:
            if sys.platform == "darwin":
                from AppKit import NSEvent, NSScreen

                point = NSEvent.mouseLocation()
                height = NSScreen.mainScreen().frame().size.height
                return (float(point.x), float(height - point.y)), NSEvent.pressedMouseButtons() > 0
            if sys.platform == "win32":
                import ctypes
                from ctypes import wintypes

                point = wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
                return (float(point.x), float(point.y)), bool(ctypes.windll.user32.GetKeyState(0x01) & 0x8000)
        except Exception:
            pass
        return None, False

    def set_regions(self, robot, panel):
        self.regions["robot"] = robot
        self.regions["panel"] = panel
        self.ignore_state = None

    @staticmethod
    def _inside(rect, px, py):
        if not rect:
            return False
        return rect["x"] <= px <= rect["x"] + rect["w"] and rect["y"] <= py <= rect["y"] + rect["h"]

    def set_click_through(self, ignore):
        if self.ignore_state == ignore:
            return
        self.ignore_state = ignore
        try:
            if sys.platform == "darwin":
                native = getattr(self.win, "native", None)
                if native is not None and hasattr(native, "setIgnoresMouseEvents_"):
                    from PyObjCTools import AppHelper

                    AppHelper.callAfter(native.setIgnoresMouseEvents_, bool(ignore))
            elif sys.platform == "win32":
                import ctypes

                hwnd = int(self.win.native.Handle)
                style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                if ignore:
                    style |= 0x00080000 | 0x00000020
                else:
                    style &= ~0x00000020
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    def track(self):
        point, down = self.cursor()
        if point is None:
            self.hover = False
            return
        px, py = point[0] - self.x, point[1] - self.y
        over_robot = self._inside(self.regions["robot"], px, py)
        over_panel = self._inside(self.regions["panel"], px, py)
        self.hover = over_robot or over_panel
        self.set_click_through(not self.hover)

        if down and over_robot and not self.dragging:
            self.dragging = True
            self.drag_off = (px, py)
        if self.dragging:
            if not down:
                self.dragging = False
            else:
                self.x = point[0] - self.drag_off[0]
                self.y = point[1] - self.drag_off[1]
                try:
                    self.win.move(int(self.x), int(self.y))
                except Exception:
                    pass

        if self.hover or self.dragging:
            self.last_activity = time.time()
            self.sleeping = False
        elif time.time() - self.last_activity > 180:
            self.sleeping = True

    # -------------------------------------------------- Алиса

    def make_alice(self, visible):
        try:
            win = webview.create_window(
                "Алиса", ALICE_URL, width=520, height=820,
                x=(150 if visible else -2600),
                y=(80 if visible else -2600),
                hidden=not visible,
                on_top=visible,
            )
            log("create_window ok visible=%s" % visible)
            return win
        except Exception as exc:
            log("create_window failed: %r" % exc)
            return None

    def ensure_alice(self):
        if self.alice is not None:
            return self.alice
        self.alice = self.make_alice(False)
        return self.alice

    def alice_closing(self, *args):
        log("alice closing intercepted -> invisible")
        self._alice_set(0.0, True, -2600, -2600)
        return False

    def show_alice(self):
        win = self.alice
        if win is None:
            log("no alice window, recreating")
            win = self.ensure_alice()
        if win is None:
            return False

        self._alice_set(1.0, False, 150, 80)
        return True

    def _alice_set(self, alpha, ignore, x, y):
        def act():
            try:
                win = self.alice
                native = getattr(win, "native", None)
                if native is not None:
                    try:
                        native.setAlphaValue_(alpha)
                    except Exception as exc:
                        log("alpha failed: %r" % exc)
                    try:
                        native.setIgnoresMouseEvents_(ignore)
                    except Exception as exc:
                        log("ignore failed: %r" % exc)
                win.move(x, y)
                win.show()
                log("alice alpha=%s ignore=%s" % (alpha, ignore))
            except Exception as exc:
                log("alice set failed: %r" % exc)

        if sys.platform == "darwin":
            from PyObjCTools import AppHelper

            AppHelper.callAfter(act)
        else:
            act()

    def _wake_alice(self, win):
        self._alice_set(0.0, True, -2600, -2600)

    def ask_alice(self, text):
        text = (text or "").strip()
        if not text:
            return ""
        with self.alice_lock:
            win = self.ensure_alice()
            if win is None:
                return "Не удалось открыть окно Алисы."
            self._wake_alice(win)
            time.sleep(0.45)
            try:
                page = (win.evaluate_js(BLOCKED_JS) or "").lower()
                if "устарел" in page or "unsupported" in page or "обновите браузер" in page:
                    return "Яндекс считает встроенный браузер старым. Нажмите ⌗ — откроется окно Алисы."
                before = win.evaluate_js(READ_JS) or ""
                sent = win.evaluate_js(SUBMIT_JS % json.dumps(text))
                if sent != "sent":
                    return "Не нашёл поле ввода. Откройте окно Алисы и войдите в аккаунт."
                last = ""
                stable = 0
                for _ in range(60):
                    time.sleep(0.5)
                    try:
                        now = win.evaluate_js(READ_JS) or ""
                    except Exception:
                        now = ""
                    if now and now != before:
                        if now == last:
                            stable += 1
                            if stable >= 3:
                                return now
                        else:
                            last = now
                            stable = 0
                return last or "Алиса молчит — проверьте вход и окно Алисы."
            except Exception:
                return "Ошибка связи с окном Алисы."

    # -------------------------------------------------- цикл

    def loop(self):
        tick = 0
        while not self.stop_flag:
            try:
                if self.win is not None:
                    self.track()
                    self.push()
                    tick += 1
                    if tick % 5 == 0:
                        if self.win.evaluate_js("window.TIM && window.TIM.quit") is True:
                            log("quit flag seen")
                            os._exit(0)
            except Exception:
                pass
            time.sleep(0.1)

    def push(self):
        if not self.ready or self.win is None:
            return
        try:
            self.win.evaluate_js("window.TIM && window.TIM.state(%s)"
                                 % json.dumps({"hover": self.hover, "sleep": self.sleeping}))
        except Exception:
            pass


def install_autostart():
    """Ставит LaunchAgent, чтобы Т.И.М. поднимался при входе в систему."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return
    try:
        path = os.path.expanduser("~/Library/LaunchAgents/com.tim.robot.plist")
        if os.path.exists(path):
            return
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
        log("autostart installed")
    except Exception as exc:
        log("autostart failed: %r" % exc)


def main():
    bot = Bot()
    api = Api(bot)
    window = webview.create_window(
        "Т.И.М.",
        url=resource_path("ui/index.html"),
        js_api=api,
        width=WIN_W,
        height=WIN_H,
        frameless=True,
        transparent=True,
        on_top=True,
        resizable=False,
        easy_drag=False,
        shadow=False,
        background_color="#000000",
    )
    bot.win = window
    bot.alice = webview.create_window(
        "Алиса", ALICE_URL, width=520, height=820, x=150, y=80, hidden=True, on_top=False
    )
    bot.alice.events.closing += bot.alice_closing
    bot.setup_position()
    window.events.loaded += lambda: bot.on_ready()
    window.events.closed += lambda *a: os._exit(0)
    install_autostart()
    webview.start(bot.loop, http_server=True, debug=False, user_agent=UA)


if __name__ == "__main__":
    main()
