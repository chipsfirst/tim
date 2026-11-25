"""Маленький робот на рабочем столе: слоистое окно с попиксельной прозрачностью.

Рисуется Pillow, показывается через UpdateLayeredWindow. Клики мимо робота
проваливаются в приложения под ним (WM_NCHITTEST отдаёт HTTRANSPARENT там,
где пиксель прозрачный), фокус окно никогда не забирает.
"""

import ctypes
import random
import threading
import time
from ctypes import wintypes

from PIL import Image, ImageDraw

user32 = ctypes.windll.user32
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 ctypes.c_size_t, ctypes.c_ssize_t]

W, H = 130, 156
WING = 16  # поля под крылья по бокам корпуса
WB = W + WING * 2
SCALE = 180 / W  # 180 px по ширине корпуса
DW, DH = int(WB * SCALE), int(H * SCALE)

WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
CS_DROPSHADOW = 0x00020000

ULW_ALPHA = 0x00000002
AC_SRC_ALPHA = 0x00000001
AC_SRC_OVER = 0x00

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_NCHITTEST = 0x0084
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
HTTRANSPARENT = -1
HTCLIENT = 1

SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004

CASE = (238, 232, 216)
CASE_EDGE = (118, 109, 92)
SCREEN = (8, 18, 9)
SCAN = (5, 13, 7)
EYE = (110, 255, 165)
PUPIL = (12, 44, 22)
MOUTH = (60, 255, 134)

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             ctypes.c_size_t, ctypes.c_ssize_t)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


FACES = ("idle", "blink", "left", "right", "happy", "laugh", "sleep",
         "think", "sad", "angry", "surprise", "wink", "curious",
         "love", "dizzy", "yawn", "smirk")

# глаза, брови, взгляд (влево/вправо), рот
SPECS = {
    "idle":     ("open", "flat", 0, "smile"),
    "blink":    ("closed", "flat", 0, "smile"),
    "left":     ("open", "flat", -1, "smile"),
    "right":    ("open", "flat", 1, "smile"),
    "happy":    ("squint", "high", 0, "smile"),
    "laugh":    ("happy", "high", 0, "grin"),
    "sleep":    ("closed", "down", 0, "tiny"),
    "think":    ("up", "one_up", 0, "o"),
    "sad":      ("half", "worried", 0, "frown"),
    "angry":    ("squint", "angry", 0, "flat"),
    "surprise": ("wide", "high", 0, "o"),
    "wink":     ("wink", "flat", 0, "smile"),
    "curious":  ("open", "one_up", 1, "tiny"),
    "love":     ("heart", "high", 0, "grin"),
    "dizzy":    ("cross", "down", 0, "o"),
    "yawn":     ("closed", "down", 0, "o"),
    "smirk":    ("half", "one_up", 0, "smile"),
}


DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}

ICONS = {
    "batt": ("0110", "1111", "1001", "1001", "1111"),
    "hp": ("01010", "11111", "11111", "01110", "00100"),
    "sleep": ("0111", "1100", "1000", "1100", "0111"),
}

# Строка показателей на экране: заряд, здоровье, сон.
STAT_KEYS = (("batt", (255, 226, 138)),
             ("hp", (255, 156, 150)),
             ("sleep", (168, 214, 255)))


def _bitmap(d, x, y, rows, color, k=1):
    for row, line in enumerate(rows):
        for col, bit in enumerate(line):
            if bit == "1":
                if k == 1:
                    d.point((x + col, y + row), fill=color)
                else:
                    d.rectangle([x + col * k, y + row * k,
                                 x + col * k + k - 1, y + row * k + k - 1], fill=color)


def draw_stats(stats, size=None):
    """Слой шкал на готовом кадре: цифры не масштабируются и остаются чёткими."""
    width, height = size or (DW, DH)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = max(1, int(round(width / 100.0)))  # 180 px → цифры вдвое крупнее
    glyph_w = 3 * k + k
    group = 5 * k + k + 3 * glyph_w
    # Ряд живёт внутри экрана, а не от края окна: считаем от рамки кинескопа.
    left = int((WING + 13) * SCALE)
    right = int((WING + W - 13) * SCALE)
    gap = max(2, (right - left - 3 * group) // 4)
    x = left + gap
    step = group + gap
    y = int(12 * SCALE) + max(3, int(4 * SCALE))
    for key, color in STAT_KEYS:
        _bitmap(d, x, y, ICONS[key], color, k)
        value = str(max(0, min(999, int(stats.get(key, 100)))))
        for index, ch in enumerate(value):
            glyph = DIGITS.get(ch)
            if glyph:
                _bitmap(d, x + 5 * k + k + index * glyph_w, y, glyph, color, k)
        x += step
    return img


KEYS = ("power", "menu", "sleep", "sound")
KEY_Y = 114
KEY_R = 9
KEY_INK = (86, 79, 64)
KEY_FACE = (226, 219, 202)


def key_box(index):
    """Прямоугольник кнопки на корпусе: четыре штуки в ряд под экраном."""
    step = 26
    cx = (W - step * 3) // 2 + index * step
    return cx - KEY_R, KEY_Y - KEY_R, cx + KEY_R, KEY_Y + KEY_R


def work_area():
    """Рабочая область без панели задач — куда можно улететь."""
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def key_at(px, py):
    for index, name in enumerate(KEYS):
        x0, y0, x1, y1 = key_box(index)
        if x0 - 1 <= px <= x1 + 1 and y0 - 1 <= py <= y1 + 1:
            return name
    return None


def _draw_keys(d):
    for index, name in enumerate(KEYS):
        box = key_box(index)
        d.ellipse(box, fill=KEY_FACE, outline=CASE_EDGE)
        cx = (box[0] + box[2]) // 2
        if name == "power":
            d.arc([cx - 4, KEY_Y - 5, cx + 4, KEY_Y + 3], 300, 240, fill=KEY_INK)
            d.line([cx, KEY_Y - 5, cx, KEY_Y - 2], fill=KEY_INK)
        elif name == "menu":
            for dy in (-3, 0, 3):
                d.line([cx - 4, KEY_Y + dy, cx + 4, KEY_Y + dy], fill=KEY_INK)
        elif name == "sleep":
            d.ellipse([cx - 4, KEY_Y - 5, cx + 4, KEY_Y + 3], fill=KEY_INK)
            d.ellipse([cx - 1, KEY_Y - 6, cx + 6, KEY_Y + 2], fill=KEY_FACE)
        else:  # sound
            d.polygon([(cx - 5, KEY_Y - 1), (cx - 2, KEY_Y - 1), (cx + 1, KEY_Y - 5),
                       (cx + 1, KEY_Y + 3), (cx - 2, KEY_Y + 2), (cx - 5, KEY_Y + 2)],
                      fill=KEY_INK)
            d.arc([cx + 1, KEY_Y - 4, cx + 7, KEY_Y + 4], 300, 60, fill=KEY_INK)


def draw_robot(face="idle", cosmetics=()):
    """Кадр робота: маленький кинескоп с живой мимикой."""
    cosmetics = cosmetics or ()
    eye, brow, look, mouth = SPECS.get(face, SPECS["idle"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # корпус
    d.rounded_rectangle([7, 4, W - 7, 128], radius=11, fill=CASE,
                        outline=CASE_EDGE, width=2)
    d.rounded_rectangle([13, 12, W - 13, 96], radius=6, fill=SCREEN,
                        outline=(33, 33, 26))

    for y in range(14, 96, 3):
        d.line([15, y, W - 15, y], fill=SCAN)

    # геометрия лица: всё считается от центра экрана
    screen_x, screen_y = 13, 12
    screen_w, screen_h = W - 26, 84
    eye_w, eye_h = 14, 11
    gap = 26
    total = eye_w * 2 + gap
    left = screen_x + (screen_w - total) // 2
    right = left + eye_w + gap
    block_h = 3 + 3 + eye_h + 8 + 8
    top = 44  # ниже строки показателей
    eye_y = top
    mouth_y = eye_y + eye_h + 8

    for x in (left, right):
        if eye == "closed":
            d.rectangle([x, eye_y + 6, x + eye_w, eye_y + 9], fill=EYE)
        elif eye == "happy":
            d.line([x, eye_y + 9, x + 10, eye_y + 5], fill=EYE, width=3)
            d.line([x + 10, eye_y + 5, x + eye_w, eye_y + 9], fill=EYE, width=3)
        elif eye == "half":
            d.rectangle([x, eye_y + 6, x + eye_w, eye_y + eye_h], fill=EYE)
        elif eye == "squint":
            d.rectangle([x, eye_y + 3, x + eye_w, eye_y + 10], fill=EYE)
        elif eye == "wide":
            d.rectangle([x - 1, eye_y - 3, x + eye_w + 1, eye_y + eye_h + 1], fill=EYE)
        elif eye == "up":
            d.rectangle([x, eye_y - 2, x + eye_w, eye_y + eye_h - 2], fill=EYE)
        elif eye == "wink" and x == right:
            d.rectangle([x, eye_y + 6, x + eye_w, eye_y + 9], fill=EYE)
        elif eye == "heart":
            _bitmap(d, x + 4, eye_y + 1, ICONS["hp"], (255, 120, 150), 1)
        elif eye == "cross":
            d.line([x + 3, eye_y + 2, x + 10, eye_y + 9], fill=EYE, width=2)
            d.line([x + 10, eye_y + 2, x + 3, eye_y + 9], fill=EYE, width=2)
        else:  # open
            d.rectangle([x, eye_y, x + eye_w, eye_y + eye_h], fill=EYE)

    # рот
    cx = W // 2
    my = mouth_y
    if mouth == "smile":
        d.rectangle([cx - 17, my + 1, cx - 8, my + 4], fill=MOUTH)
        d.rectangle([cx - 8, my + 4, cx + 8, my + 7], fill=MOUTH)
        d.rectangle([cx + 8, my + 1, cx + 17, my + 4], fill=MOUTH)
    elif mouth == "grin":
        d.rectangle([cx - 18, my - 1, cx + 18, my + 8], fill=MOUTH)
        d.rectangle([cx - 13, my + 1, cx + 13, my + 6], fill=PUPIL)
    elif mouth == "flat":
        d.rectangle([cx - 17, my + 2, cx + 17, my + 5], fill=MOUTH)
    elif mouth == "frown":
        d.rectangle([cx - 17, my + 5, cx - 8, my + 8], fill=MOUTH)
        d.rectangle([cx - 8, my + 2, cx + 8, my + 5], fill=MOUTH)
        d.rectangle([cx + 8, my + 5, cx + 17, my + 8], fill=MOUTH)
    elif mouth == "o":
        d.rectangle([cx - 8, my + 1, cx + 8, my + 10], fill=MOUTH)
        d.rectangle([cx - 4, my + 4, cx + 4, my + 8], fill=PUPIL)
    else:  # tiny
        d.rectangle([cx - 8, my + 2, cx + 8, my + 4], fill=MOUTH)

    # кнопки на корпусе
    _draw_keys(d)

    # косметика: шарф на шее, очки поверх глаз, шляпа на макушке
    if "scarf" in cosmetics:
        d.rectangle([13, 97, W - 13, 104], fill=(196, 86, 74))
        d.rectangle([13, 100, W - 13, 102], fill=(176, 72, 62))
    if "glasses" in cosmetics:
        for x in (left, right):
            d.rectangle([x - 2, eye_y - 2, x + eye_w + 2, eye_y + eye_h + 2],
                        outline=(150, 205, 215), width=1)
        d.line([left + eye_w + 2, eye_y + eye_h // 2,
                right - 2, eye_y + eye_h // 2], fill=(150, 205, 215))
    if "hat" in cosmetics:
        d.rectangle([W // 2 - 28, 9, W // 2 + 28, 12], fill=(58, 52, 46))
        d.rectangle([W // 2 - 16, 0, W // 2 + 16, 9], fill=(58, 52, 46))
        d.rectangle([W // 2 - 16, 6, W // 2 + 16, 9], fill=(170, 64, 58))

    # подставка
    d.polygon([(W // 2 - 9, 128), (W // 2 + 9, 128), (W // 2 + 13, 141), (W // 2 - 13, 141)],
              fill=(173, 162, 139), outline=CASE_EDGE)
    d.rounded_rectangle([W // 2 - 27, 141, W // 2 + 27, 151], radius=4,
                        fill=(201, 193, 174), outline=CASE_EDGE, width=2)
    return img


def body_frame(face="idle", cosmetics=()):
    """Корпус по центру широкого холста: по краям место для крыльев."""
    canvas = Image.new("RGBA", (WB, H), (0, 0, 0, 0))
    canvas.alpha_composite(draw_robot(face, cosmetics), (WING, 0))
    return canvas


def draw_wings(flap=False):
    """Крылья по бокам корпуса: два положения маха."""
    img = Image.new("RGBA", (WB, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lift = -7 if flap else 3
    for side in (0, 1):
        edge = WING + (7 if side == 0 else W - 7)
        direction = -1 if side == 0 else 1
        for i in range(3):
            y0 = 36 + i * 13
            length = WING - 2 - i * 3
            tip_x, tip_y = edge + direction * length, y0 + lift + i * 4
            d.line([edge, y0, tip_x, tip_y], fill=(240, 234, 219), width=3)
            d.line([edge, y0 + 1, tip_x, tip_y + 1], fill=(168, 158, 134), width=1)
    return img


def premultiplied(image):
    """Pillow RGBA → BGRA с предумноженной альфой и маска непрозрачности."""
    width, height = image.size
    data = bytearray(width * height * 4)
    mask = bytearray(width * height)
    pixels = image.load()
    index = 0
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            mask[y * width + x] = 1 if a > 24 else 0
            if a:
                data[index] = (b * a) // 255
                data[index + 1] = (g * a) // 255
                data[index + 2] = (r * a) // 255
                data[index + 3] = a
            index += 4
    return bytes(data), mask


class Mascot:
    """Окно-робот. Живёт в своём потоке с циклом сообщений Windows."""

    def __init__(self, on_click=None, on_right_click=None, on_move=None, on_key=None,
                 log=None, cosmetics=()):
        self.on_click = on_click
        self.on_right_click = on_right_click
        self.on_move = on_move
        self.on_key = on_key
        self.log = log or (lambda msg: None)
        self.cosmetics = frozenset(cosmetics or ())
        self._frames_dirty = False
        self.hwnd = None
        self.face = "idle"
        self.mask = None
        self.frames = {}
        self.base_frames = {}
        self._composed = {}
        self.stats = {"batt": 100, "hp": 100, "sleep": 100}
        self.flying = False
        self._flap = False
        self._flap_count = 0
        self._fly_target = None
        self._fly_pause = 0.0
        self._thread = None
        self._stop = False
        self._dragging = False
        self._drag_from = (0, 0)
        self._drag_start = (0, 0)
        self._moved = 0
        self._last_up = 0.0
        self._last_blink = time.time()
        self._blink_until = 0.0
        self._mimic = "happy"
        self._mimic_until = 0.0
        self._last_mimic = time.time()
        self._proc = WNDPROC(self._wndproc)

    # ------------------------------------------------------------ кадры

    def _prepare(self):
        for name in FACES:
            img = body_frame(name, self.cosmetics)
            self.base_frames[name] = img
            data, mask = premultiplied(img.resize((DW, DH), Image.LANCZOS))
            self.frames[name] = data
            if name == "idle":
                self.mask = mask

    def set_cosmetics(self, items):
        """Купленная косметика: пересобираем кадры в потоке окна."""
        items = frozenset(items or ())
        if items == self.cosmetics:
            return
        self.cosmetics = items
        # Готовые кадры собраны из старых базовых: без сброса кэша
        # покупка не появится до смены мимики.
        self._composed.clear()
        self._frames_dirty = True
        self._pending_repaint = True

    def _frame(self, face):
        """Кадр лица плюс крылья и шкалы: значения меняются на лету."""
        if self._frames_dirty:
            self._frames_dirty = False
            self._prepare()
        base = self.frames.get(face) or self.frames["idle"]
        if not self.base_frames:
            return base
        key = (face, self.stats["batt"], self.stats["hp"], self.stats["sleep"],
               self._flap if self.flying else None)
        cached = self._composed.get(key)
        if cached is not None:
            return cached
        # цифры рисуем уже после уменьшения: иначе 5-пиксельные глифы
        # размазываются и шкалы не прочитать.
        img = self.base_frames.get(face, self.base_frames["idle"]).resize(
            (DW, DH), Image.LANCZOS).copy()
        if self.flying:
            img.alpha_composite(draw_wings(self._flap).resize((DW, DH), Image.LANCZOS))
        img.alpha_composite(draw_stats(self.stats, (DW, DH)))
        data, _ = premultiplied(img)
        if len(self._composed) > 60:
            self._composed.clear()
        self._composed[key] = data
        return data

    def set_stats(self, stats):
        changed = False
        for key in ("batt", "hp", "sleep"):
            try:
                value = max(0, min(999, int(round(float(stats.get(key, 100))))))
            except (TypeError, ValueError):
                continue
            if self.stats.get(key) != value:
                self.stats[key] = value
                changed = True
        if changed:
            self._pending_repaint = True

    def _current_face(self):
        now = time.time()
        if now < self._blink_until:
            return "blink"
        if self.face == "idle" and now < self._mimic_until:
            return self._mimic
        return self.face if self.face in self.frames else "idle"

    # ------------------------------------------------------------ окно

    def start(self, x, y):
        self._prepare()
        self._thread = threading.Thread(target=self._run, args=(x, y), daemon=True)
        self._thread.start()

    def _run(self, x, y):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASS()
        wc.style = 0
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
        wc.hbrBackground = None
        wc.lpszClassName = "TimMascotWindow"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # класс уже зарегистрирован
                self.log("mascot: RegisterClass %s" % err)
                return
        style = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(
            style, "TimMascotWindow", "Т.И.М.", WS_POPUP,
            int(x), int(y), DW, DH, None, None, hinst, None)
        if not self.hwnd:
            self.log("mascot: CreateWindowEx %s" % ctypes.get_last_error())
            return
        self._paint()
        user32.ShowWindow(self.hwnd, 8)  # SW_SHOWNA
        self.log("mascot ok")
        user32.SetTimer(self.hwnd, 1, 100, None)
        msg = wintypes.MSG()
        while not self._stop and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _paint(self):
        if not self.hwnd:
            return
        face = self._current_face()
        data = self._frame(face)
        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = DW
        info.bmiHeader.biHeight = -DH  # сверху вниз
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(screen_dc, ctypes.byref(info), 0,
                                        ctypes.byref(bits), None, 0)
        if not bitmap:
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, screen_dc)
            return
        ctypes.memmove(bits, data, len(data))
        old = gdi32.SelectObject(mem_dc, bitmap)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        size = wintypes.SIZE(DW, DH)
        src = wintypes.POINT(0, 0)
        user32.UpdateLayeredWindow(self.hwnd, screen_dc, None, ctypes.byref(size),
                                   mem_dc, ctypes.byref(src), 0, ctypes.byref(blend),
                                   ULW_ALPHA)
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_NCHITTEST:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            point = wintypes.POINT(x, y)
            user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(self._rect))
            rx = x - self._rect.left
            ry = y - self._rect.top
            if self.mask and 0 <= rx < DW and 0 <= ry < DH and self.mask[ry * DW + rx]:
                return HTCLIENT
            return HTTRANSPARENT
        if msg == WM_TIMER:
            self._tick()
            return 0
        if msg == WM_LBUTTONDOWN:
            self._dragging = True
            self._moved = 0
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            self._drag_from = (point.x, point.y)
            user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(self._rect))
            self._drag_start = (self._rect.left, self._rect.top)
            user32.SetCapture(wintypes.HWND(hwnd))
            return 0
        if msg == WM_MOUSEMOVE and self._dragging:
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            dx = point.x - self._drag_from[0]
            dy = point.y - self._drag_from[1]
            self._moved = max(self._moved, abs(dx) + abs(dy))
            user32.SetWindowPos(wintypes.HWND(hwnd), None,
                                self._drag_start[0] + dx, self._drag_start[1] + dy,
                                0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            if self.on_move:
                self.on_move()
            return 0
        if msg == WM_LBUTTONUP:
            now = time.time()
            was = self._dragging
            self._dragging = False
            user32.ReleaseCapture()
            # Иногда один клик приходит двумя WM_LBUTTONUP: без дребезга
            # кнопка питания выключила бы робота первым же нажатием.
            if now - self._last_up < 0.25:
                return 0
            self._last_up = now
            if was and self._moved < 4:
                point = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(point))
                user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(self._rect))
                key = key_at((point.x - self._rect.left) / SCALE - WING,
                             (point.y - self._rect.top) / SCALE)
                if key and self.on_key:
                    self.on_key(key)
                elif self.on_click:
                    self.on_click()
            return 0
        if msg == WM_RBUTTONUP:
            if self.on_right_click:
                self.on_right_click()
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(wintypes.HWND(hwnd))
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(wintypes.HWND(hwnd), msg, wparam, lparam)

    _rect = wintypes.RECT()

    def _tick(self):
        """Раз в 100 мс: моргание, случайная мимика и перерисовка кадра."""
        now = time.time()
        changed = False
        if self._blink_until and now >= self._blink_until:
            self._blink_until = 0.0
            changed = True
        if not self._blink_until and now - self._last_blink > 4.0:
            self._blink_until = now + 0.14
            self._last_blink = now
            changed = True
        if self.face == "idle":
            if self._mimic_until and now >= self._mimic_until:
                self._mimic_until = 0.0
                changed = True
            elif not self._mimic_until and now - self._last_mimic > 6 and random.random() < 0.08:
                self._mimic = random.choice(
                    ("happy", "wink", "curious", "surprise", "laugh", "love", "smirk"))
                self._mimic_until = now + random.uniform(0.8, 1.6)
                self._last_mimic = now
                changed = True
        if self.flying:
            changed = self._fly_tick() or changed
        if changed or self._pending_repaint:
            self._pending_repaint = False
            self._paint()

    _pending_repaint = False

    # ------------------------------------------------------------ снаружи

    def set_face(self, face):
        if face == self.face:
            return
        self.face = face
        self._pending_repaint = True

    def position(self):
        if not self.hwnd:
            return 0, 0
        user32.GetWindowRect(wintypes.HWND(self.hwnd), ctypes.byref(self._rect))
        return self._rect.left, self._rect.top

    def move(self, x, y):
        if self.hwnd:
            user32.SetWindowPos(wintypes.HWND(self.hwnd), None, int(x), int(y),
                                0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)

    def set_flying(self, on):
        on = bool(on)
        if on == self.flying:
            return
        self.flying = on
        self._fly_target = None
        self._fly_pause = 0.0
        self._pending_repaint = True

    def _random_target(self):
        wx, wy, ww, wh = work_area()
        cx, cy = self.position()
        max_x = max(wx, wx + ww - DW)
        max_y = max(wy, wy + wh - DH)
        target = (wx, wy)
        for _ in range(8):
            target = (random.randint(wx, max_x), random.randint(wy, max_y))
            if abs(target[0] - cx) + abs(target[1] - cy) > 140:
                break
        return target

    def _fly_tick(self):
        """Шаг полёта: мах крыльями и движение к случайной точке экрана."""
        self._flap_count += 1
        flap = (self._flap_count // 2) % 2 == 1
        changed = False
        if flap != self._flap:
            self._flap = flap
            changed = True
        if not self.hwnd:
            return changed
        if time.time() < self._fly_pause:
            return changed
        cx, cy = self.position()
        if self._fly_target is None:
            self._fly_target = self._random_target()
            return changed
        tx, ty = self._fly_target
        dx, dy = tx - cx, ty - cy
        dist = max(abs(dx), abs(dy))
        if dist <= 6:
            self._fly_target = None
            self._fly_pause = time.time() + random.uniform(0.4, 1.4)
            return changed
        step = min(16, dist)
        nx = cx + int(round(dx / dist * step))
        ny = cy + int(round(dy / dist * step))
        self.move(nx, ny)
        if self.on_move:
            self.on_move()
        return changed

    def stop(self):
        self._stop = True
        if self.hwnd:
            user32.PostMessageW(wintypes.HWND(self.hwnd), WM_CLOSE, 0, 0)
