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
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Без явных типов ctypes режет 64-битные хендлы регионов до int.
gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.CreatePolygonRgn.restype = ctypes.c_void_p
gdi32.CreatePolygonRgn.argtypes = [ctypes.POINTER(wintypes.POINT), ctypes.c_int, ctypes.c_int]
gdi32.CombineRgn.restype = ctypes.c_int
gdi32.CombineRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
user32.SetWindowRgn.restype = ctypes.c_int
user32.SetWindowRgn.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "TIM-screen-companion"
_mutex = None  # держим хэндл: с его закрытием мьютекс освобождается

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
VK_LBUTTON = 0x01
MOUSEEVENTF_LEFTDOWN = 0x0002

OWNS_DRAG = True    # перетаскивание в своём потоке

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


def find_window(win):
    """Окно pywebview по заголовку — без ожидания, для формы облачка."""
    title = getattr(win, "title", "") or ""
    return user32.FindWindowW(None, title) if title else None


def hwnd_of(win):
    """Хендл окна: сначала через нативный объект, поиск по заголовку — запасной.

    int() на System.IntPtr падает, поэтому Handle приводится через ToInt64.
    """
    for _ in range(50):
        try:
            native = getattr(win, "native", None)
            if native is not None:
                handle = native.Handle
                value = handle.ToInt64() if hasattr(handle, "ToInt64") else int(handle)
                if value:
                    return int(value)
        except Exception:
            pass
        # Запасной путь — по заголовку окна: у каждого окна он свой, иначе
        # поиск «Т.И.М.» возвращал робота вместо облачка.
        title = getattr(win, "title", "") or ""
        found = user32.FindWindowW(None, title) if title else None
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
        width, height = window_size(self.hwnd)
        if width and height:
            self.bot.win_w, self.bot.win_h = width, height
        round_corners(self.hwnd)
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
        if not regions.get("robot"):
            # Резерв: пока страница не прислала зоны, считаем роботом
            # нижнюю половину окна — иначе перетаскивание мертво.
            w = getattr(bot, "win_w", 340)
            h = getattr(bot, "win_h", 500)
            regions = {"robot": {"x": (w - 250) / 2, "y": h - 286,
                                 "w": 250, "h": 286}, "panel": None, "extra": []}
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
            bot.move_cloud()

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
            if getattr(bot, "win", None) is None:
                # Режим робота: монитора нет, показываем облачко.
                bot.open_bubble()
                return
            handle = hwnd_of(bot.win) or 0
            if handle:
                user32.ShowWindow(handle, 9)
                user32.SetForegroundWindow(handle)
            bot.focus_input()

        menu = pystray.Menu(
            pystray.MenuItem("Показать", lambda: on_show(), default=True),
            # В режиме робота страницы монитора нет — звук переключаем в Bot.
            pystray.MenuItem("Звук", lambda: bot.toggle_sound()
                             if hasattr(bot, "toggle_sound") else bot.toggle_sound_js()),
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
            # Alt+Space занят системным меню окна — берём Ctrl+Alt+Space.
            MOD_ALT, MOD_CONTROL, VK_SPACE, WM_HOTKEY = 0x0001, 0x0002, 0x20, 0x0312
            if not user32.RegisterHotKey(None, 1, MOD_ALT | MOD_CONTROL, VK_SPACE):
                bot.log("win hotkey busy")
                return
            bot.log("hotkey ok (ctrl+alt+space, win)")
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    bot.focus_input()
        except Exception as exc:
            bot.log("win hotkey failed: %r" % exc)

    threading.Thread(target=run, daemon=True).start()


def already_running():
    """Второй экземпляр не нужен: два робота, два трея и отнятый хоткей."""
    global _mutex
    try:
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return False
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            return True
        _mutex = handle
        return False
    except Exception:
        return False


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


def setup():
    dpi_setup()


def move_window(win, x, y):
    handle = hwnd_of(win)
    if handle:
        move(handle, x, y)


def set_click_through(win, ignore):
    """На Windows окно скруглено регионом, отдельная прозрачность не нужна."""
    return None


RADIUS = 16
RGN_OR = 2
WS_EX_TOOLWINDOW = 0x00000080

SW_SHOWNOACTIVATE = 4


def show_window(hwnd, visible=True):
    """Показ и скрытие без активации: окно облачка не должно забирать фокус."""
    if not hwnd:
        return False
    try:
        user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOWNOACTIVATE if visible else 0)
        return True
    except Exception:
        return False


def foreground_is(hwnd):
    """Наше ли окно сейчас в фокусе: чтобы не отбирать его у пользователя."""
    return bool(hwnd) and user32.GetForegroundWindow() == hwnd


WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002
GWL_EXSTYLE = -20


def ghost(hwnd):
    """Окно видимо для Windows и невидимо глазу: скрытое окно Chromium душит.

    Клики сквозь него не проходят — поэтому окно ещё и уводим за экран.
    """
    if not hwnd:
        return False
    try:
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style | WS_EX_LAYERED)
        ok = bool(user32.SetLayeredWindowAttributes(wintypes.HWND(hwnd), 0, 0, LWA_ALPHA))
        user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOWNOACTIVATE)
        return ok
    except Exception:
        return False


def clear_ghost(hwnd):
    """Возвращает окну обычную видимость: под ним открывается вход."""
    if not hwnd:
        return False
    try:
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style & ~WS_EX_LAYERED)
        return True
    except Exception:
        return False


def window_size(hwnd):
    """Фактический размер окна: pywebview создаёт его меньше запрошенного."""
    rect = wintypes.RECT()
    if not hwnd or not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return 0, 0
    return rect.right - rect.left, rect.bottom - rect.top


def round_corners(hwnd):
    """Скругляет углы окна один раз при старте.

    Регион статичный: менять его на лету нельзя — WebView2 не успевает
    перерисовать появившуюся область и часть окна остаётся пустой.
    """
    if not hwnd:
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return False
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, RADIUS, RADIUS)
    if not region:
        return False
    # SetWindowRgn забирает регион себе — удалять его после вызова нельзя.
    return bool(user32.SetWindowRgn(wintypes.HWND(hwnd), region, True))


def shape_bubble(hwnd, tail=14, radius=14):
    """Форма облачка: скруглённое тело плюс треугольный хвостик снизу.

    Форма статичная — окно облачка не меняет размер, поэтому перерисовка
    WebView2 не страдает.
    """
    if not hwnd:
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return False
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height - tail + 1, radius, radius)
    if not region:
        return False
    if tail > 0:
        points = (wintypes.POINT * 3)()
        middle = width // 2
        points[0].x, points[0].y = middle - 9, height - tail - 1
        points[1].x, points[1].y = middle + 9, height - tail - 1
        points[2].x, points[2].y = middle, height
        triangle = gdi32.CreatePolygonRgn(points, 3, 1)
        if triangle:
            gdi32.CombineRgn(region, region, triangle, RGN_OR)
            gdi32.DeleteObject(triangle)
    return bool(user32.SetWindowRgn(wintypes.HWND(hwnd), region, True))


def make_tool_window(hwnd):
    """Убирает облачко из панели задач и Alt+Tab: это всплывающая подсказка."""
    if not hwnd:
        return False
    try:
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        if not style & WS_EX_TOOLWINDOW:
            user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE,
                                  style | WS_EX_TOOLWINDOW)
        return True
    except Exception:
        return False


def start_drag(bot):
    Drag(bot).start()


def call_soon(fn):
    fn()


def autostart_enabled():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, "TIM")
            return True
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_autostart(enabled):
    if enabled:
        return install_autostart()
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, "TIM")
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def focus_window(hwnd):
    """Отдаёт окну фокус: без этого печатать в облачко некуда."""
    if not hwnd:
        return False
    target = wintypes.HWND(hwnd)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    tid_fg = user32.GetWindowThreadProcessId(wintypes.HWND(fg), None) if fg else 0
    tid_me = kernel32.GetCurrentThreadId()
    attached = False
    try:
        if tid_fg and tid_fg != tid_me:
            attached = bool(user32.AttachThreadInput(tid_me, tid_fg, True))
        user32.SetForegroundWindow(target)
        user32.SetFocus(target)
    except Exception:
        pass
    finally:
        if attached:
            user32.AttachThreadInput(tid_me, tid_fg, False)
    return user32.GetForegroundWindow() == hwnd


def activate(bot):
    """Поднимает окно поверх и отдаёт ему фокус — иначе клики уходят мимо."""
    handle = hwnd_of(bot.win)
    if not handle:
        return False
    try:
        user32.ShowWindow(handle, 5)
        user32.SetWindowPos(wintypes.HWND(handle), wintypes.HWND(HWND_TOPMOST),
                            0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        user32.SetForegroundWindow(handle)
        return True
    except Exception as exc:
        bot.log("activate: %r" % exc)
        return False
