"""Всё, что касается Windows: окно, перетаскивание, трей, хоткей, автозапуск.

Логика нарочно отделена от macOS-ветки: на Windows окно двигается напрямую
через Win32 (SetWindowPos), без маршалинга в UI-поток pywebview. Иначе частые
вызовы window.move() подвешивают WinForms.
"""

import ctypes
import os
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
VK_LBUTTON = 0x01
MOUSEEVENTF_LEFTDOWN = 0x0002

TICK = 1.0 / 60.0          # частота перетаскивания
REACH = 2                  # запас попадания в зону, px


def dpi_setup():
    """Физические пиксели: иначе координаты окна и курсора расходятся."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def work_area():
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def cursor():
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        return None, False
    down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    return (float(point.x), float(point.y)), down


def hwnd_of(win):
    for _ in range(50):
        try:
            native = getattr(win, "native", None)
            if native is not None:
                handle = int(native.Handle)
                if handle:
                    return handle
        except Exception:
            pass
        found = user32.FindWindowW(None, "Т.И.М.")
        if found:
            return found
        time.sleep(0.2)
    return None


def move(hwnd, x, y):
    ok = user32.SetWindowPos(
        wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST),
        int(x), int(y), 0, 0,
        SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    return bool(ok)


def inside(rect, px, py):
    if not rect:
        return False
    return (rect["x"] - REACH <= px <= rect["x"] + rect["w"] + REACH
            and rect["y"] - REACH <= py <= rect["y"] + rect["h"] + REACH)


class Drag:
    """Перетаскивание и наведение: свой поток, Win32 напрямую."""

    def __init__(self, bot):
        self.bot = bot
        self.hwnd = None
        self.dragging = False
        self.offset = (0.0, 0.0)

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        self.hwnd = hwnd_of(self.bot.win)
        if not self.hwnd:
            self.bot.log("win drag: окно не найдено")
            return
        self.bot.log("win drag ok")
        bot = self.bot
        while not bot.stop_flag:
            try:
                self.step()
            except Exception as exc:
                bot.log("win drag: %r" % exc)
                time.sleep(0.5)
            time.sleep(TICK)

    def step(self):
        bot = self.bot
        point, down = cursor()
        if point is None:
            bot.hover = False
            return

        px = point[0] - bot.x
        py = point[1] - bot.y
        regions = bot.regions
        over = (inside(regions.get("robot"), px, py)
                or inside(regions.get("panel"), px, py)
                or any(inside(r, px, py) for r in regions.get("extra") or []))

        if down and over and not self.dragging:
            self.dragging = True
            self.offset = (px, py)

        if self.dragging and not down:
            self.dragging = False

        if self.dragging and down:
            bot.x = point[0] - self.offset[0]
            bot.y = point[1] - self.offset[1]
            move(self.hwnd, bot.x, bot.y)

        bot.hover = over
        if over or self.dragging:
            bot.last_activity = time.time()
            bot.sleeping = False
        elif time.time() - bot.last_activity > 180:
            bot.sleeping = True


def start_tray(bot):
    def run():
        try:
            import pystray
            from PIL import Image
        except Exception as exc:
            bot.log("win tray import failed: %r" % exc)
            return
        try:
            image = Image.open(bot.resource("ui/icon.png"))
        except Exception as exc:
            bot.log("win tray icon failed: %r" % exc)
            image = None

        def on_show():
            handle = hwnd_of(bot.win) or 0
            if handle:
                user32.ShowWindow(handle, 9)
                user32.SetForegroundWindow(handle)
            bot.focus_input()

        menu = pystray.Menu(
            pystray.MenuItem("Показать", lambda: on_show(), default=True),
            pystray.MenuItem("Звук", lambda: bot.toggle_sound_js()),
            pystray.MenuItem("Выход", lambda: os._exit(0)),
        )
        try:
            icon = pystray.Icon("TIM", image, "Т.И.М.", menu)
            icon.run()
        except Exception as exc:
            bot.log("win tray failed: %r" % exc)

    threading.Thread(target=run, daemon=True).start()


def start_hotkey(bot):
    def run():
        try:
            MOD_ALT, VK_SPACE, WM_HOTKEY = 0x0001, 0x20, 0x0312
            if not user32.RegisterHotKey(None, 1, MOD_ALT, VK_SPACE):
                bot.log("win hotkey busy")
                return
            bot.log("hotkey ok (alt+space, win)")
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    bot.focus_input()
        except Exception as exc:
            bot.log("win hotkey failed: %r" % exc)

    threading.Thread(target=run, daemon=True).start()


def install_autostart():
    if not getattr(__import__("sys"), "frozen", False):
        return False
    try:
        import winreg

        exe = os.path.abspath(__import__("sys").executable)
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
            winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "TIM", 0, winreg.REG_SZ, '"%s"' % exe)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
