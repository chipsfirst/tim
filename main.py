#!/usr/bin/env python3
"""Т.И.М. — техническая иммерсивная модель в углу экрана.

Стоит на месте, живёт глазами, попискивает как R2-D2 и умеет спрашивать
Алису через браузерное окно. Кот Поля живёт отдельно и это не затрагивает.
"""

import json
import os
import random
import subprocess
import sys
import threading
import time

import webview

import platform_impl as plat

APP_DIR = os.path.dirname(os.path.abspath(__file__))

ALICE_URL = "https://alice.yandex.ru/"

if sys.platform == "win32":
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
else:
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BLOCKED_JS = "(document.body && document.body.innerText || '').slice(0, 600)"
READ_TAIL_JS = "(document.body && document.body.innerText || '').slice(-3000)"
# Служебные строки интерфейса, которые попадают в хвост страницы.
UI_MARKERS = ("Спросите о чём", "Хороший ответ", "Плохой ответ", "Выключить звук", "Интеллект:", "Алиса старается", "Настройки", "Новый чат", "Студия", "Для учёбы")

READ_JS = """
(function () {
  var nodes = document.querySelectorAll('[class*="message"], [class*="Message"], [data-testid*="message"], [class*="reply"], [class*="answer"]');
  for (var i = nodes.length - 1; i >= 0; i--) {
    var t = (nodes[i].innerText || "").replace(/\\s+/g, " ").trim();
    if (t.length >= 12) return t.slice(0, 10000);
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


def log_path():
    if sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Logs")
    else:
        base = os.environ.get("TEMP") or os.path.expanduser("~")
    return os.path.join(base, "TIM.log")


def log(msg, level="info"):
    """Пишет в TIM.log. Файл ротируется на мегабайте, чтобы не рос бесконечно."""
    try:
        path = log_path()
        if os.path.exists(path) and os.path.getsize(path) > 1024 * 1024:
            try:
                os.replace(path, path + ".1")
            except OSError:
                pass
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("%s %-5s %s\n" % (time.strftime("%H:%M:%S"), level, msg))
    except Exception:
        pass


def guard(where, exc):
    """Единая точка для подавленных исключений — молча больше не глотаем."""
    log("%s: %r" % (where, exc), "warn")

def load_config():
    try:
        with open(resource_path("ui/config.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        log("config: %r" % exc, "warn")
        return {}


CONFIG = load_config()
WINDOW_CFG = CONFIG.get("window", {})
LOOP_CFG = CONFIG.get("loop", {})

WIN_W = int(WINDOW_CFG.get("width", 340))
WIN_H = int(WINDOW_CFG.get("height", 500))

# Облачко — отдельное окно над монитором: тело и хвостик, 14px внизу.
CLOUD_W = 340
CLOUD_H = 240
CLOUD_TAIL = 0

# Кормление даёт монету, поэтому не чаще раза в 10 минут.
FEED_COOLDOWN = 600
# Зарядка: батарея садится, её надо поднимать.
CHARGE_COOLDOWN = 180

# Сброс ожидания корма или зарядки за монеты.
RESET_COST = 2

# Лавка: что можно купить и сколько это стоит.
SHOP = {"hat": 15, "glasses": 10, "scarf": 8, "antenna": 12, "mustache": 8,
        "halo": 25, "beard": 18, "paint_blue": 20, "paint_gold": 30,
        "paint_red": 20, "paint_green": 20}

# Робот время от времени говорит сам — мотивация и всякая чепуха.
PHRASES = (
    "Отдохни минуту. Я послежу за курсором.",
    "Ты сегодня уже лучше, чем вчера. Я проверял.",
    "Если задача не идёт — она просто не знает, кто здесь главный.",
    "Сделай глоток воды. Ну пожалуйста.",
    "Я верю в тебя. У меня, правда, нет выбора — я же твой робот.",
    "Пять минут без экрана — и мысли встанут на место.",
    "Помни: идеальный код — это код, который не пришлось писать.",
    "Ты не обязан быть продуктивным каждую секунду.",
    "Сложное делится на маленькое. Я проверял на себе.",
    "Небольшой перерыв — это часть работы, а не отговорка.",
    "Сегодня отличный день, чтобы сделать одну маленькую вещь.",
    "Ошибки — это просто карта того, что уже проверено.",
    "Раз я стою ровно — значит, и у тебя всё получится.",
    "У меня 100% батареи и полная уверенность в тебе.",
    "Если что — я всегда на рабочем столе. Почти буквально.",
    "Чай остынет. Это я намекаю.",
    "Даже роботы иногда просто смотрят в стену. Мигаю.",
    "Ты держишься лучше, чем выглядит со стороны.",
    "Начни с самого маленького шага. Дальше пойдёт.",
    "Порядок в папках — порядок в голове. Шутка. Почти.",
    "Я умею хранить секреты. Правда, до перезагрузки.",
    "Прямо сейчас кто-то застрял на той же задаче. Ты не один.",
)

# Мелодии спикером: только общественное достояние — народные и свои.
# Темы из фильмов и игр 80-х под копирайтом, их здесь нет.
MELODIES = {
    "тетрис": ((659, 140), (494, 140), (523, 140), (587, 140), (523, 140), (494, 140),
               (440, 140), (440, 140), (523, 140), (659, 140), (587, 140), (523, 140),
               (494, 140), (494, 140), (523, 140), (587, 140), (659, 140), (523, 140),
               (440, 140), (440, 280)),
    "чижик": ((349, 180), (349, 180), (392, 180), (392, 180),
              (349, 180), (349, 180), (330, 360)),
    "джингл": ((523, 110), (659, 110), (784, 110), (1047, 220),
               (784, 110), (659, 110), (523, 220)),
}


def state_path():
    if sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "TIM")
    else:
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "TIM")
    return os.path.join(base, "state.json")


STATE_VERSION = 1


def read_state():
    try:
        with open(state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    version = data.pop("v", 0)
    if version == STATE_VERSION:
        return data
    # Миграция: старые файлы без версии — просто набор шкал.
    log("state migrated from v%s" % version, "warn")
    return data


def write_state(data):
    try:
        path = state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        payload = dict(data or {})
        payload["v"] = STATE_VERSION
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        guard("write_state", exc)
        return False


def latest_tag():
    """Спрашивает у GitHub последний релиз. Пустая строка — не вышло."""
    import urllib.request

    url = "https://api.github.com/repos/chipsfirst/tim/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TIM"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.load(resp).get("tag_name", "")
    except Exception as exc:
        guard("latest_tag", exc)
        return ""


_WEATHER = {"at": 0.0, "data": None}


def _http_json(url, timeout=8):
    """Простой GET JSON: погода и геолокация идут отсюда, а не из страницы."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "TIM"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def weather_now():
    """Погода по IP: город, координаты и температура. Кэш на 10 минут."""
    now = time.time()
    if _WEATHER["data"] and now - _WEATHER["at"] < 600:
        return _WEATHER["data"]
    lat, lon, city = 55.75, 37.62, "Москва"
    try:
        geo = _http_json("https://ipwho.is/")
        if geo.get("latitude") is not None:
            lat, lon = float(geo["latitude"]), float(geo["longitude"])
            city = geo.get("city") or city
    except Exception as exc:
        guard("geo", exc)
    try:
        url = ("https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
               "&current=temperature_2m,weather_code&timezone=auto" % (lat, lon))
        data = _http_json(url)
        cur = data.get("current") or {}
        result = {
            "ok": "temperature_2m" in cur,
            "temp": int(round(cur.get("temperature_2m") or 0)),
            "code": cur.get("weather_code"),
            "city": city,
            "at": (cur.get("time") or "")[11:16],
        }
    except Exception as exc:
        guard("weather", exc)
        result = {"ok": False, "city": city}
    _WEATHER["data"] = result
    _WEATHER["at"] = now
    return result


class Api:
    def __init__(self, bot):
        self._bot = bot

    def ready(self):
        self._bot.on_ready()

    def set_regions(self, robot, panel, extra=None):
        self._bot.set_regions(robot, panel, extra)

    def set_panel(self, is_open):
        self._bot.panel_open = bool(is_open)
        self._bot.ignore_state = None

    def ask(self, text):
        log("ask from ui: %r" % (text or "")[:40])
        bot = self._bot
        bot.set_face("think")
        bot.asking = True
        try:
            answer = bot.ask_alice(text)
        finally:
            bot.asking = False
        log("answer: %d chars: %r" % (len(answer or ""), (answer or "")[:80]))
        bot.set_face("happy" if answer else "dizzy")
        threading.Timer(1.8, lambda: bot.set_face("idle")).start()
        if answer and not answer.startswith("Нужно войти"):
            bot.add_coins(1)
        return answer

    def sleep(self):
        """Усыпляет робота: ближайший клик по нему разбудит."""
        self._bot.set_face("sleep")
        log("sleep requested")
        return True

    def sound_state(self):
        return bool(self._bot.sound)

    def sound_toggle(self):
        return self._bot.toggle_sound()

    def login(self):
        log("login pressed")
        return "opened" if self._bot.show_alice() else "failed"

    def cancel(self):
        """Прерывает ожидание ответа: цикл в ask_alice увидит флаг и выйдет."""
        self._bot.cancel_ask = True
        log("cancel pressed")
        return True

    def say(self, text, thinking=0):
        """Показывает ответ в окне-облачке — страница монитора текст не рисует."""
        return self._bot.show_cloud(text, bool(thinking))

    def hide_cloud(self):
        return self._bot.hide_cloud()

    def cloud_ready(self):
        """Страница облачка загрузилась позже ответа — отдаём текст заново."""
        if self._bot.cloud_visible and self._bot.cloud_text:
            return self._bot.show_cloud(self._bot.cloud_text, self._bot.cloud_thinking)
        return True

    def load_stats(self):
        return read_state()

    def stats(self):
        return self._bot.public_stats()

    def feed(self):
        log("feed pressed")
        return self._bot.feed()

    def charge(self):
        log("charge pressed")
        return self._bot.charge()

    def dance(self):
        log("dance pressed")
        return self._bot.dance()

    def fly(self):
        log("fly pressed")
        return self._bot.toggle_fly()

    def add_coins(self, n=1):
        """Монеты за игры: страница зовёт их сама."""
        self._bot.add_coins(int(n or 1))
        return self._bot.public_stats()

    def buy(self, item):
        return self._bot.buy(item)

    def wear(self, item, on=True):
        return self._bot.wear(item, on)

    def shop(self):
        return self._bot.shop_state()

    def reset_cooldown(self, kind):
        return self._bot.reset_cooldown(kind)

    def save_last(self, text):
        self._bot.last_answer = str(text or "")[:12000]
        return True

    def last(self):
        return getattr(self._bot, "last_answer", "")

    def save_stats(self, data):
        return write_state(data if isinstance(data, dict) else {})

    def toggle_expand(self):
        log("toggle_expand called")
        bot = self._bot
        bot.expanded = not getattr(bot, "expanded", False)
        w, h = (WIN_W + 180, WIN_H + 220) if bot.expanded else (WIN_W, WIN_H)
        log("resize -> %dx%d" % (w, h))
        try:
            bot.win.resize(int(w), int(h))
        except Exception as exc:
            guard("resize", exc)
            return {"ok": False, "error": repr(exc), "wide": bot.expanded}
        bot.win_w, bot.win_h = w, h
        try:
            bot.setup_position()
            plat.move_window(bot.win, bot.x, bot.y)
        except Exception as exc:
            guard("expand move", exc)
        return {"ok": True, "w": w, "h": h, "wide": bot.expanded}

    def autostart_toggle(self):
        state = not plat.autostart_enabled()
        ok = plat.set_autostart(state)
        return state if ok else None

    def check_update(self):
        return latest_tag()

    def weather(self):
        return weather_now()

    def melody(self):
        return self._bot.play_melody()

    def log_js(self, message, source="", line=0, level="error"):
        # Уровень приходит со страницы: обычные отметки не должны шуметь как ошибки.
        if level not in ("info", "warn", "error"):
            level = "error"
        log("js: %s (%s:%s)" % (str(message)[:400], source, line), level)
        return True

    def quit(self):
        self._bot.quit()


class Bot:
    def __init__(self):
        self.win = None
        self.ready = False
        self.placed = False
        self.stop_flag = False
        state = read_state()
        self.sound = bool(state.get("sound", False))
        # Шкалы и монеты держим в Python: облачко может быть спрятано,
        # а тикать жизнь робота должна всё равно.
        self.stats = {
            "batt": float(state.get("batt", 100) or 0),
            "hp": float(state.get("hp", 100) or 0),
            "sleep": float(state.get("sleep", 100) or 0),
            "xp": int(state.get("xp", 0) or 0),
            "coins": int(state.get("coins", 0) or 0),
        }
        self.warned = {}
        self.last_feed = float(state.get("last_feed", 0) or 0)
        self.last_charge = float(state.get("last_charge", 0) or 0)
        self.quit_armed = 0.0
        worn = state.get("cosmetics") or []
        self.cosmetics = set(x for x in worn if x in SHOP) if isinstance(worn, list) else set()
        # Старые профили не знали «куплено» отдельно: что надето, то и куплено.
        # None (поля нет) — не то же самое, что пустой список: иначе надетое
        # снова становится товаром в лавке.
        bought = state.get("owned")
        self.owned = (set(x for x in bought if x in SHOP) if isinstance(bought, list)
                      else set(self.cosmetics))
        self.owned |= self.cosmetics
        self._phrase = ""

        self.regions = {"robot": None, "panel": None, "extra": []}
        self.hover = False
        self.panel_open = False
        self.menu_open = False
        self.ignore_state = None

        self.x = 0.0
        self.y = 0.0

        self.alice = None
        self.alice_lock = threading.Lock()
        self._alice_hwnd = None
        self.cancel_ask = False
        self.asking = False
        self.btn_sound = True

        self.cloud = None
        self.cloud_visible = False
        self.cloud_shaped = False
        self.cloud_text = ""
        self.cloud_thinking = False
        self.cloud_hwnd = None
        self.cloud_w = CLOUD_W
        self.cloud_h = CLOUD_H

        self.mascot = None
        self.mascot_w = 110
        self.mascot_h = 124

        self.dragging = False
        self.drag_off = (0.0, 0.0)
        self.last_activity = time.time()
        self.sleeping = False

    # -------------------------------------------------- окно

    def work_area(self):
        area = plat.work_area()
        if area:
            return area
        screen = webview.screens[0]
        return screen.x, screen.y, screen.width, screen.height

    def setup_position(self):
        wx, wy, ww, wh = self.work_area()
        w = getattr(self, "win_w", WIN_W)
        h = getattr(self, "win_h", WIN_H)
        self.x = float(wx + ww - w - int(WINDOW_CFG.get("margin_right", 12)))
        self.y = float(wy + wh - h - int(WINDOW_CFG.get("margin_bottom", 2)))

    def place(self):
        if self.placed or self.win is None:
            return
        try:
            plat.move_window(self.win, self.x, self.y)
            self.placed = True
        except Exception as exc:
            guard("place", exc)

    # -------------------------------------------------- робот

    def start_mascot(self):
        import mascot as mascot_mod

        self.mascot_w, self.mascot_h = mascot_mod.DW, mascot_mod.DH
        wx, wy, ww, wh = self.work_area()
        x = wx + ww - self.mascot_w - 48
        y = wy + wh - self.mascot_h - 64
        self.mascot = mascot_mod.Mascot(
            on_click=self.on_mascot_click, on_move=self.move_cloud,
            on_key=self.on_mascot_key, log=log, cosmetics=self.cosmetics)
        self.mascot.start(x, y)
        self.mascot.set_stats(self.public_stats())

    def on_mascot_key(self, key):
        """Кнопки на корпусе робота: питание, меню, сон, звук."""
        log("mascot key %s" % key)
        if key == "power":
            now = time.time()
            if now < self.quit_armed:
                self.quit()
                return
            self.quit_armed = now + 3
            self.show_cloud("Выключить Т.И.М.? Нажми кнопку питания ещё раз.", False)
            return
        if key == "menu":
            self.open_bubble()
            try:
                self.cloud.evaluate_js("window.cloud && window.cloud.menu(true)")
            except Exception as exc:
                guard("menu key", exc)
            return
        if key == "sleep":
            self.flying = False
            if self.mascot is not None:
                self.mascot.set_flying(False)
            self.set_face("sleep")
            self.hide_cloud()
            return
        if key == "sound":
            self.toggle_sound()

    def toggle_sound(self):
        """Единая точка: кнопка на корпусе, трей и облачко должны совпадать."""
        self.sound = not self.sound
        log("sound %s" % ("on" if self.sound else "off"))
        self.save_stats()
        self.push_sound()
        self.chirp("ok" if self.sound else "bad")
        return self.sound

    def on_mascot_click(self):
        log("mascot click")
        self.set_face("idle")
        if self.cloud_visible:
            self.hide_cloud()
            return
        self.open_bubble()

    def open_bubble(self):
        self.show_cloud(self.cloud_text, False)
        self.chirp("blip")
        try:
            import win_backend

            handle = self.cloud_hwnd or win_backend.hwnd_of(self.cloud)
            self.cloud_hwnd = handle
            log("focus cloud: %s" % win_backend.focus_window(handle))
            # Каретку ставим с задержкой: окно активируется не мгновенно.
            threading.Timer(0.15, self._focus_cloud_input).start()
        except Exception as exc:
            guard("focus cloud", exc)
    def _focus_cloud_input(self):
        if self.cloud is None:
            return
        try:
            self.cloud.evaluate_js("window.cloud && window.cloud.focusInput()")
        except Exception as exc:
            guard("focus cloud input", exc)

    def set_face(self, face):
        if self.mascot is not None:
            self.mascot.set_face(face)

    # -------------------------------------------------- жизнь робота

    def public_stats(self):
        keys = ("batt", "hp", "sleep", "xp", "coins")
        return {k: int(round(self.stats[k])) for k in keys}

    def start_stats(self):
        threading.Thread(target=self._stats_loop, daemon=True).start()
        threading.Thread(target=self._ambient_loop, daemon=True).start()
        threading.Thread(target=self._phrase_loop, daemon=True).start()
        threading.Thread(target=self._melody_loop, daemon=True).start()

    def _stats_loop(self):
        ticks = 0
        while True:
            time.sleep(15)
            ticks += 1
            try:
                self.stats_tick(save=not ticks % 4)
            except Exception as exc:
                guard("stats_tick", exc)

    def stats_tick(self, save=True):
        st = self.stats
        asleep = getattr(self.mascot, "face", "") == "sleep"
        st["batt"] = max(0.0, min(100.0, st["batt"] + (0.35 if asleep else -0.12)))
        st["sleep"] = max(0.0, min(100.0, st["sleep"] + (2.2 if asleep else -0.2)))
        if st["batt"] < 20 or st["sleep"] < 15:
            st["hp"] = max(0.0, st["hp"] - 0.12)
        else:
            st["hp"] = min(100.0, st["hp"] + 0.05)
        if st["hp"] > 50 and st["batt"] > 30 and st["sleep"] > 40:
            st["xp"] += 1
            if st["xp"] % 100 == 0:
                log("level up: %d" % (1 + st["xp"] // 100))
                self.set_face("laugh")
                threading.Timer(1.6, lambda: self.set_face("idle")).start()
                self.chirp("ok")

        if st["batt"] < 20 and not self.warned.get("batt"):
            self.warned["batt"] = True
            self.set_face("sad")
            self.chirp("bad")
        elif st["batt"] > 40:
            self.warned["batt"] = False

        if st["hp"] < 30 and not self.warned.get("hp"):
            self.warned["hp"] = True
            self.set_face("sad")
            self.chirp("bad")
        elif st["hp"] > 55:
            self.warned["hp"] = False

        if st["sleep"] < 15 and not self.warned.get("sleep"):
            self.warned["sleep"] = True
            self.set_face("sleep")
            self.chirp("ok")
        elif st["sleep"] > 45:
            self.warned["sleep"] = False

        if save:
            self.save_stats()
        self.push_stats()

    def save_stats(self):
        try:
            data = read_state()
            for key in ("batt", "hp", "sleep", "xp", "coins"):
                data[key] = self.stats[key]
            data["last_feed"] = self.last_feed
            data["last_charge"] = self.last_charge
            data["sound"] = self.sound
            data["cosmetics"] = sorted(self.cosmetics)
            data["owned"] = sorted(self.owned)
            write_state(data)
        except Exception as exc:
            guard("save_stats", exc)

    def push_stats(self):
        if self.mascot is not None:
            self.mascot.set_stats(self.public_stats())
        if self.cloud is None or not self.cloud_visible:
            return
        try:
            self.cloud.evaluate_js("window.cloud && window.cloud.stats(%s)"
                                   % json.dumps(self.public_stats()))
        except Exception as exc:
            guard("push_stats", exc)

    def push_sound(self):
        if self.cloud is None:
            return
        try:
            self.cloud.evaluate_js("window.cloud && window.cloud.setSound(%s)"
                                   % json.dumps(bool(self.sound)))
        except Exception as exc:
            guard("push_sound", exc)

    def chirp(self, kind="blip"):
        """Пищалки рисует страница облачка: свой WebAudio-движок."""
        if self.cloud is None:
            return False
        try:
            self.cloud.evaluate_js("window.cloud && window.cloud.chirp(%s)" % json.dumps(kind))
            return True
        except Exception as exc:
            guard("chirp", exc)
            return False

    def _ambient_loop(self):
        """Робот потихоньку попискивает сам по себе."""
        while True:
            time.sleep(random.uniform(35, 80))
            self.chirp("blip")

    def _phrase_loop(self):
        """Раз в 15–30 минут робот говорит что-нибудь от себя."""
        time.sleep(random.uniform(60, 180))
        while True:
            try:
                self.say_phrase()
            except Exception as exc:
                guard("phrase", exc)
            time.sleep(random.uniform(900, 1800))

    def _melody_loop(self):
        """Раз в 20–40 минут — короткая мелодия, если звук включён."""
        time.sleep(random.uniform(120, 300))
        while True:
            try:
                if self.sound and not self.asking:
                    self.play_melody()
            except Exception as exc:
                guard("melody loop", exc)
            time.sleep(random.uniform(1200, 2400))

    def play_melody(self, name=None):
        """Пищит спикером: работает и без клика по облачку."""
        if not self.sound or sys.platform != "win32" or not MELODIES:
            return ""
        if name not in MELODIES:
            name = random.choice(list(MELODIES))
        notes = MELODIES[name]

        def run():
            try:
                import winsound

                for freq, ms in notes:
                    winsound.Beep(int(freq), int(ms))
            except Exception as exc:
                guard("melody", exc)

        threading.Thread(target=run, daemon=True).start()
        log("melody %s" % name)
        return name

    def say_phrase(self):
        if self.cloud is None or self.cloud_visible or self.asking:
            return False
        if self.mascot is not None and self.mascot.face == "sleep":
            return False
        phrase = random.choice(PHRASES)
        if not self.show_cloud(phrase, False):
            return False
        self._phrase = phrase
        self.set_face(random.choice(("happy", "cool", "wink", "peace")))
        threading.Timer(2.0, lambda: self.set_face("idle")).start()
        threading.Timer(24, self._hide_phrase).start()
        self.chirp("blip")
        log("phrase shown")
        return True

    def _hide_phrase(self):
        """Закрывает только свою фразу: ответ Алисы не трогаем."""
        if self.cloud_visible and self.cloud_text == self._phrase:
            self.hide_cloud()

    def reset_cooldown(self, kind):
        """Сброс ожидания корма или зарядки за монеты."""
        wait = self._wait_left(kind)
        if wait is None:
            return {"ok": False, "why": "unknown", "stats": self.public_stats()}
        if wait <= 0:
            return {"ok": False, "why": "ready", "stats": self.public_stats()}
        if self.stats["coins"] < RESET_COST:
            self.chirp("bad")
            return {"ok": False, "why": "coins", "need": RESET_COST,
                    "stats": self.public_stats()}
        self.stats["coins"] -= RESET_COST
        if kind == "feed":
            self.last_feed = 0.0
        else:
            self.last_charge = 0.0
        self.save_stats()
        self.push_stats()
        log("reset %s for coins" % kind)
        return {"ok": True, "stats": self.public_stats()}

    def _wait_left(self, kind):
        now = time.time()
        if kind == "feed":
            return int(FEED_COOLDOWN - (now - self.last_feed))
        if kind == "charge":
            return int(CHARGE_COOLDOWN - (now - self.last_charge))
        return None

    def buy(self, item):
        price = SHOP.get(item)
        if price is None:
            return {"ok": False, "why": "unknown", "stats": self.public_stats()}
        if item in self.owned:
            return {"ok": False, "why": "owned", "stats": self.public_stats()}
        if self.stats["coins"] < price:
            self.chirp("bad")
            return {"ok": False, "why": "coins", "need": price,
                    "stats": self.public_stats()}
        self.stats["coins"] -= price
        self.owned.add(item)
        self.cosmetics.add(item)
        self.save_stats()
        self.push_stats()
        if self.mascot is not None:
            self.mascot.set_cosmetics(self.cosmetics)
        self.chirp("coin")
        self.set_face("cheeky")
        threading.Timer(1.4, lambda: self.set_face("idle")).start()
        log("bought %s for %d" % (item, price))
        return {"ok": True, "stats": self.public_stats(),
                "owned": sorted(self.cosmetics)}

    def wear(self, item, on=True):
        """Снять или надеть уже купленную вещь: деньги не тратятся."""
        state = {"stats": self.public_stats(), "owned": sorted(self.owned),
                 "worn": sorted(self.cosmetics)}
        if item not in SHOP:
            state.update(ok=False, why="unknown")
            return state
        if item not in self.owned:
            state.update(ok=False, why="not_owned")
            return state
        if on:
            self.cosmetics.add(item)
        else:
            self.cosmetics.discard(item)
        self.save_stats()
        self.push_stats()
        if self.mascot is not None:
            self.mascot.set_cosmetics(self.cosmetics)
        log("%s %s" % ("wore" if on else "wore off", item))
        state.update(ok=True, worn=sorted(self.cosmetics))
        return state

    def shop_state(self):
        return {"coins": int(self.stats["coins"]), "prices": dict(SHOP),
                "owned": sorted(self.owned), "worn": sorted(self.cosmetics)}

    def add_coins(self, n=1):
        self.stats["coins"] = int(self.stats["coins"]) + int(n)
        log("coins: %d" % self.stats["coins"])
        self.save_stats()
        self.push_stats()
        self.chirp("coin")

    def feed(self):
        now = time.time()
        wait = int(FEED_COOLDOWN - (now - self.last_feed))
        if wait > 0:
            self.chirp("bad")
            return {"ok": False, "wait": wait, "stats": self.public_stats()}
        st = self.stats
        st["hp"] = min(100.0, st["hp"] + 15)
        st["sleep"] = min(100.0, st["sleep"] + 5)
        st["batt"] = min(100.0, st["batt"] + 3)
        self.last_feed = now
        self.save_stats()
        self.set_face("love")
        threading.Timer(1.2, lambda: self.set_face("idle")).start()
        self.add_coins(1)
        return {"ok": True, "stats": self.public_stats()}

    def charge(self):
        """Зарядка: +25 к батарее, не чаще раза в три минуты."""
        now = time.time()
        wait = int(CHARGE_COOLDOWN - (now - self.last_charge))
        if wait > 0:
            self.chirp("bad")
            return {"ok": False, "wait": wait, "stats": self.public_stats()}
        self.stats["batt"] = min(100.0, self.stats["batt"] + 25)
        self.last_charge = now
        self.save_stats()
        self.push_stats()
        self.set_face("happy")
        threading.Timer(1.2, lambda: self.set_face("idle")).start()
        self.chirp("ok")
        return {"ok": True, "wait": 0, "stats": self.public_stats()}

    def toggle_fly(self):
        """Режим полёта: робот отращивает крылья и сам летает по экрану."""
        self.flying = not getattr(self, "flying", False)
        if self.mascot is not None:
            self.mascot.set_flying(self.flying)
        log("fly %s" % ("on" if self.flying else "off"))
        return self.flying

    def dance(self):
        def run():
            for face, delay in (("happy", 0.4), ("wink", 0.4), ("laugh", 0.5),
                                ("surprise", 0.4), ("love", 0.5), ("smirk", 0.4),
                                ("idle", 0.0)):
                self.set_face(face)
                time.sleep(delay)

        threading.Thread(target=run, daemon=True).start()
        self.chirp("ok")
        return True


    # -------------------------------------------------- облачко

    def cloud_position(self):
        """Облачко лежит прямо на мониторе: без хвостика и зазоров."""
        if self.mascot is not None:
            mx, my = self.mascot.position()
            x = mx + (self.mascot_w - self.cloud_w) / 2
            y = my + 2 - self.cloud_h
        else:
            x = self.x + (getattr(self, "win_w", WIN_W) - self.cloud_w) / 2
            y = self.y + 2 - self.cloud_h
        wx, wy, ww, wh = self.work_area()
        x = min(max(x, wx), wx + ww - self.cloud_w)
        y = max(y, wy)
        return int(x), int(y)

    def show_cloud(self, text, thinking=False):
        cloud = self.cloud
        if cloud is None:
            return False
        self.cloud_text = str(text or "")[:12000]
        self.cloud_thinking = bool(thinking)
        self.shape_cloud()
        x, y = self.cloud_position()
        script = ("window.cloud && window.cloud.show.apply(null, %s)"
                  % json.dumps([self.cloud_text, self.cloud_thinking]))
        try:
            if self.cloud_hwnd:
                import win_backend

                win_backend.move(self.cloud_hwnd, x, y)
            else:
                cloud.move(x, y)
            cloud.show()
            self.cloud_visible = True
            cloud.evaluate_js(script)
            log("cloud show at %d,%d" % (x, y))
            return True
        except Exception as exc:
            guard("show_cloud", exc)
            return False

    def hide_cloud(self):
        cloud = self.cloud
        if cloud is None or not self.cloud_visible:
            return False
        try:
            if self.cloud_hwnd:
                import win_backend

                win_backend.show_window(self.cloud_hwnd, False)
            else:
                cloud.hide()
            self.cloud_visible = False
            log("cloud hide")
            return True
        except Exception as exc:
            guard("hide_cloud", exc)
            return False

    def move_cloud(self):
        """Двигает облачко за роботом: напрямую, без маршалинга."""
        if self.cloud is None or not self.cloud_visible:
            return
        x, y = self.cloud_position()
        if sys.platform == "win32":
            import win_backend

            if self.cloud_hwnd is None:
                self.cloud_hwnd = win_backend.hwnd_of(self.cloud)
            if self.cloud_hwnd:
                win_backend.move(self.cloud_hwnd, x, y)
                return
        try:
            self.cloud.move(x, y)
        except Exception as exc:
            guard("move_cloud", exc)

    def shape_cloud(self):
        """Скругление и форма окна — один раз: регион на лету менять нельзя."""
        if self.cloud_shaped or sys.platform != "win32" or self.cloud is None:
            return
        try:
            import win_backend

            handle = self.cloud_hwnd or win_backend.find_window(self.cloud)
            if not handle:
                return
            self.cloud_hwnd = handle
            width, height = win_backend.window_size(handle)
            if width and height:
                self.cloud_w, self.cloud_h = width, height
            win_backend.shape_bubble(handle, CLOUD_TAIL)
            win_backend.make_tool_window(handle)
            self.cloud_shaped = True
            log("cloud shaped %dx%d" % (self.cloud_w, self.cloud_h))
        except Exception as exc:
            guard("shape_cloud", exc)

    def shape_cloud_soon(self):
        for _ in range(50):
            if self.cloud_shaped or self.cloud is None:
                return
            self.shape_cloud()
            time.sleep(0.2)

    def on_ready(self):
        if self.ready:
            return
        self.ready = True
        log("ready")
        threading.Thread(target=self.shape_cloud_soon, daemon=True).start()

    def focus_input(self):
        """Горячая клавиша и трей: в режиме робота поле живёт в облачке."""
        if sys.platform == "win32" and self.cloud is not None:
            self.open_bubble()
            return
        try:
            self.win.evaluate_js(
                "document.getElementById('q') && document.getElementById('q').focus()")
        except Exception as exc:
            guard("focus_input", exc)

    def toggle_sound_js(self):
        try:
            self.win.evaluate_js(
                "document.getElementById('sound')"
                ".dispatchEvent(new MouseEvent('click',{bubbles:true}))")
        except Exception as exc:
            guard("toggle_sound_js", exc)

    def resource(self, rel):
        return resource_path(rel)

    def log(self, msg, level="info"):
        log(msg, level)

    def start_tray(self):
        plat.start_tray(self)

    def start_hotkey(self):
        plat.start_hotkey(self)

    def quit(self):
        log("quit requested")
        os._exit(0)

    # -------------------------------------------------- зоны старого монитора

    def set_regions(self, robot, panel, extra=None):
        self.regions = {"robot": robot, "panel": panel, "extra": list(extra or [])}

    @staticmethod
    def _inside(rect, px, py):
        if not rect:
            return False
        return (rect["x"] <= px <= rect["x"] + rect["w"]
                and rect["y"] <= py <= rect["y"] + rect["h"])

    def cursor(self):
        try:
            return plat.cursor()
        except Exception as exc:
            guard("cursor", exc)
            return None, False

    def track(self):
        return self.cursor()

    def set_click_through(self, ignore):
        if self.win is None:
            return
        try:
            plat.set_click_through(self.win, bool(ignore))
        except Exception as exc:
            guard("set_click_through", exc)

    def loop(self):
        while not self.stop_flag:
            time.sleep(0.05)

    def push(self):
        time.sleep(0.05)

    # -------------------------------------------------- Алиса

    def make_alice(self, visible):
        win = self.alice
        if win is None:
            return None
        if visible:
            try:
                win.show()
            except Exception as exc:
                guard("make_alice", exc)
        return win

    def _alice_ok(self, win):
        try:
            return win.evaluate_js("1+1") == 2
        except Exception:
            return False

    def _create_alice(self):
        def act():
            try:
                win = webview.create_window(
                    "Алиса", ALICE_URL, width=520, height=820,
                    x=150, y=80, hidden=True, on_top=False)
                win.events.closing += self.alice_closing
                self.alice = win
                log("alice window created")
            except Exception as exc:
                guard("alice create", exc)

        plat.call_soon(act)

    def ensure_alice(self):
        """Окно Алисы могло быть закрыто — тогда поднимаем новое."""
        win = self.alice
        if win is not None and self._alice_ok(win):
            return win
        log("alice: окна нет, создаю новое")
        self._create_alice()
        for _ in range(40):
            win = self.alice
            if win is not None and self._alice_ok(win):
                return win
            time.sleep(0.5)
        return self.alice

    def alice_closing(self, *args):
        log("alice window closing")
        # Окно закрыли руками — забудем его, ensure_alice создаст новое.
        self.alice = None
        self._alice_hwnd = None
        return True

    def show_alice(self):
        with self.alice_lock:
            win = self.ensure_alice()
            if win is None:
                return False
            self._alice_set(1.0, False, 150, 80)
            return True

    def _alice_set(self, alpha, ignore, x, y):
        """Скрывает или показывает окно Алисы.

        При alpha = 0 на Windows окно остаётся видимым для системы, но
        полностью прозрачным: скрытое окно Chromium душит и ответа не дождаться.
        """
        def act():
            try:
                win = self.alice
                if win is None:
                    return
                if sys.platform == "win32":
                    import win_backend

                    hwnd = self._alice_hwnd
                    if not hwnd:
                        hwnd = win_backend.hwnd_of(win)
                        self._alice_hwnd = hwnd
                    if not hwnd:
                        log("alice set: окна нет")
                        return
                    if alpha > 0:
                        win_backend.clear_ghost(hwnd)
                        win.move(x, y)
                        win.show()
                    else:
                        win_backend.ghost(hwnd)
                else:
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

        plat.call_soon(act)

    def _wake_alice(self, win):
        """Прячет окно Алисы невидимо для задач."""
        self._alice_set(0.0, True, -2600, -2600)

    def _restore_cloud_focus(self):
        """Возвращает фокус в поле облачка, если его забрала Алиса."""
        if self.cloud is None or not self.cloud_visible:
            return
        try:
            import win_backend

            handle = self.cloud_hwnd or win_backend.hwnd_of(self.cloud)
            self.cloud_hwnd = handle
            # Пользователь мог уйти в другое окно — тогда не перебиваем его.
            if self._alice_hwnd and not win_backend.foreground_is(self._alice_hwnd):
                return
            win_backend.focus_window(handle)
            threading.Timer(0.15, self._focus_cloud_input).start()
        except Exception as exc:
            guard("restore cloud focus", exc)

    @staticmethod
    def _extract_answer(tail, question):
        """Ответ = текст после вопроса до служебных строк интерфейса."""
        low = tail.lower()
        q = question.strip().lower()
        pos = -1
        start = 0
        while True:
            i = low.find(q, start)
            if i < 0:
                break
            if "алиса" in low[i:i + len(q) + 12]:
                pos = i
            start = i + 1
        if pos < 0:
            return ""
        rest = tail[pos + len(q):]
        for marker in UI_MARKERS:
            idx = rest.find(marker)
            if idx >= 0:
                rest = rest[:idx]
        rest = rest.strip()
        if rest.startswith("Алиса"):
            rest = rest[len("Алиса"):].strip()
        return rest if len(rest) >= 10 else ""

    def ask_alice(self, text):
        """Пишет вопрос в окно Алисы и ждёт ответ по DOM."""
        text = str(text or "").strip()
        if not text:
            return ""
        win = self.ensure_alice()
        if win is None:
            log("alice: окна нет", "warn")
            return ""
        self.cancel_ask = False
        # Вопрос идёт через страницу: окно Алисы не показываем, а если его
        # открыли вручную (вход) — прячем перед отправкой.
        self._wake_alice(win)
        probe = text.strip().lower()
        try:
            sent = win.evaluate_js(SUBMIT_JS % json.dumps(text))
            log("alice submit: %s" % sent)
        except Exception as exc:
            guard("alice submit", exc)
            self._wake_alice(win)
            self._restore_cloud_focus()
            return ""
        if sent == "no-input":
            log("alice: поля ввода нет — похоже, нужен вход", "warn")
            self.show_alice()
            return "Нужно войти в Алису: нажми ⌗ в облачке, войди — и спроси ещё раз."
        # Задачи отдаются только активному окну: забираем фокус в прозрачную
        # Алису и тут же возвращаем в облачко — вопрос уже отправлен.
        try:
            import win_backend

            if self._alice_hwnd:
                win_backend.focus_window(self._alice_hwnd)
        except Exception as exc:
            guard("alice focus", exc)
        self._restore_cloud_focus()
        time.sleep(0.3)
        # Баннер «Войдите в аккаунт» висит на странице всегда, даже когда
        # чат отвечает анонимно — по нему нельзя судить, есть ли сессия.
        started = time.time()
        deadline = started + 75
        candidate = ""
        while time.time() < deadline:
            if self.cancel_ask:
                log("alice: отменено")
                self._wake_alice(win)
                self._restore_cloud_focus()
                return ""
            time.sleep(0.6)
            try:
                tail = win.evaluate_js(READ_TAIL_JS) or ""
            except Exception as exc:
                guard("alice read", exc)
                continue
            now = self._extract_answer(str(tail), text)
            if not now:
                continue
            # Сайт без сессии отдаёт страницу «войдите в аккаунт» — это не ответ.
            low_now = now.lower()
            if "не удалось загрузить" in low_now:
                log("alice: чат не открылся — нужен вход", "warn")
                self.show_alice()
                return "Нужно войти в Алису: нажми ⌗ в облачке, войди — и спроси ещё раз."
            # Эхо — это вернувшийся сам вопрос, а не ответ, который просто
            # начинается с того же слова («привет» → «Привет! Рада видеть»).
            echo = now.strip().lower().rstrip(" .!?…") == probe
            if echo:
                candidate = ""
                continue
            # «Готовлю ответ, подождите» — это ещё не ответ.
            low = now.lower()
            if "готовлю ответ" in low or "подождите немного" in low:
                candidate = ""
                continue
            # ответ засчитываем, когда он два раза подряд пришёл одинаковым
            if candidate == now:
                log("alice answer: %d chars" % len(now))
                try:
                    self._wake_alice(win)
                except Exception as exc:
                    guard("alice park", exc)
                self._restore_cloud_focus()
                return now
            candidate = now
        try:
            blocked = win.evaluate_js(BLOCKED_JS) or ""
        except Exception:
            blocked = ""
        log("alice: таймаут, экран %r" % str(blocked)[:120], "warn")
        try:
            tail = str(win.evaluate_js(READ_TAIL_JS) or "")
        except Exception:
            tail = ""
        log("alice tail: %r" % tail[-500:], "warn")
        self._wake_alice(win)
        self._restore_cloud_focus()
        return ""


def _run():
    bot = Bot()
    api = Api(bot)
    if sys.platform == "win32":
        _run_mascot(bot, api)
        return
    kw = dict(
        title="Т.И.М.",
        url=resource_path("ui/index.html"),
        js_api=api,
        width=WIN_W,
        height=WIN_H,
        frameless=True,
        on_top=True,
        resizable=False,
        easy_drag=False,
    )
    kw["background_color"] = "#000000"
    if sys.platform == "darwin":
        kw["shadow"] = False
    try:
        window = webview.create_window(transparent=True, **kw)
    except (TypeError, ValueError):
        log("transparent unsupported, retry opaque")
        window = webview.create_window(transparent=False, **kw)
    bot.win = window
    bot.cloud = webview.create_window(
        # Заголовок обязан отличаться от монитора: поиск окна по имени иначе
        # находит монитор и двигает не то окно.
        "Т.И.М. — ответ", resource_path("ui/cloud.html"),
        width=CLOUD_W, height=CLOUD_H,
        frameless=True, on_top=True, hidden=True, focus=False,
        resizable=False, easy_drag=False, background_color="#000000",
    )
    bot.alice = webview.create_window(
        "Алиса", ALICE_URL, width=520, height=820, x=150, y=80, hidden=True, on_top=False
    )
    bot.alice.events.closing += bot.alice_closing
    bot.setup_position()
    window.events.loaded += lambda: bot.on_ready()
    window.events.closed += lambda *a: os._exit(0)
    install_autostart()
    webview.start(bot.loop, http_server=True, debug=False, user_agent=UA)


def _run_mascot(bot, api):
    """Windows: робот на рабочем столе плюс облачко с ответом и вводом."""
    # Окно Алисы не показываем, но страница должна работать как активная:
    # без этих флагов Chromium душит скрытое окно и ответ не приходит.
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        "--disable-background-timer-throttling "
        "--disable-renderer-backgrounding "
        "--disable-backgrounding-occluded-windows")
    bot.cloud = webview.create_window(
        "Т.И.М. — ответ", resource_path("ui/cloud.html"),
        width=CLOUD_W, height=CLOUD_H,
        frameless=True, on_top=True, hidden=True, focus=False,
        resizable=False, easy_drag=False, background_color="#000000",
        js_api=api,
    )
    bot.alice = webview.create_window(
        "Алиса", ALICE_URL, width=520, height=820, x=150, y=80, hidden=True, on_top=False
    )
    bot.alice.events.closing += bot.alice_closing
    install_autostart()
    bot.start_mascot()
    bot.start_tray()
    bot.start_hotkey()
    bot.start_stats()
    webview.start(None, http_server=True, debug=False, user_agent=UA)


def install_autostart():
    if plat.install_autostart():
        log("autostart installed")
    else:
        # Не ошибка: из исходников автозапуск не ставят.
        log("autostart skipped")


def main():
    if sys.platform == "win32":
        import win_backend

        if win_backend.already_running():
            log("уже запущен — второй экземпляр не нужен")
            return
    plat.setup()
    try:
        _run()
    except Exception:
        import traceback

        tb = traceback.format_exc()
        log("FATAL " + tb)
        try:
            if sys.platform == "win32":
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0, tb[-1500:], "Т.И.М. — ошибка запуска", 0x10)
            else:
                import subprocess

                subprocess.run(
                    ["osascript", "-e",
                     'display alert "Т.И.М. — ошибка запуска" message "%s"'
                     % tb[-400:].replace('"', "'").replace("\n", " ")],
                    check=False)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
