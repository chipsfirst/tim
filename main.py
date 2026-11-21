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

CONFIG = load_config()
WINDOW_CFG = CONFIG.get("window", {})
LOOP_CFG = CONFIG.get("loop", {})

WIN_W = int(WINDOW_CFG.get("width", 340))
WIN_H = int(WINDOW_CFG.get("height", 500))



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


class Api:
    def __init__(self, bot):
        self.bot = bot

    def ready(self):
        self.bot.on_ready()

    def set_regions(self, robot, panel, extra=None):
        self.bot.set_regions(robot, panel, extra)

    def set_panel(self, is_open):
        self.bot.panel_open = bool(is_open)
        self.bot.ignore_state = None

    def ask(self, text):
        log("ask from ui: %r" % (text or "")[:40])
        return self.bot.ask_alice(text)

    def login(self):
        log("login pressed")
        return "opened" if self.bot.show_alice() else "failed"

    def load_stats(self):
        return read_state()

    def save_stats(self, data):
        return write_state(data if isinstance(data, dict) else {})

    def toggle_expand(self):
        log("toggle_expand called")
        bot = self.bot
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

    def log_js(self, message, source="", line=0):
        level = "info" if str(message).startswith("wide click") else "error"
        log("js: %s (%s:%s)" % (str(message)[:400], source, line), level)
        return True

    def quit(self):
        self.bot.quit()


class Bot:
    def __init__(self):
        self.win = None
        self.ready = False
        self.placed = False
        self.stop_flag = False

        self.regions = {"robot": None, "panel": None, "extra": []}
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

    def on_ready(self):
        self.ready = True
        self.place()
        plat.start_drag(self)
        if sys.platform == "win32":
            import win_backend

            threading.Thread(target=lambda: (time.sleep(2.5), win_backend.activate(self)),
                             daemon=True).start()
        threading.Thread(target=self.audit_menu, daemon=True).start()
        threading.Thread(target=self.start_tray, daemon=True).start()

    def audit_menu(self):
        """Проверяет, что у каждого пункта меню есть обработчик."""
        time.sleep(3)
        try:
            bad = self.win.evaluate_js(
                "(window.TIM && window.TIM.menu) ? window.TIM.menu.audit() : ['menu']")
            if bad:
                log("menu audit: без обработчика %r" % (bad,), "error")
            else:
                log("menu audit ok")
        except Exception as exc:
            guard("audit_menu", exc)

    def log(self, msg):
        log(msg)

    def resource(self, rel):
        return resource_path(rel)

    def focus_input(self):
        try:
            self.win.evaluate_js("document.getElementById('q').focus()")
        except Exception as exc:
            guard("focus_input", exc)

    def toggle_sound_js(self):
        try:
            self.win.evaluate_js(
                "document.getElementById('sound')"
                ".dispatchEvent(new MouseEvent('click',{bubbles:true}))")
        except Exception as exc:
            guard("toggle_sound_js", exc)

    def start_tray(self):
        plat.start_tray(self)

    def start_hotkey(self):
        plat.start_hotkey(self)

    def quit(self):
        log("quit requested")
        os._exit(0)

    # -------------------------------------------------- мышь

    def set_regions(self, robot, panel, extra=None):
        self.regions["robot"] = robot
        self.regions["panel"] = panel
        self.regions["extra"] = extra if isinstance(extra, list) else []

    def cursor(self):
        return plat.cursor()

    @staticmethod
    def _inside(rect, px, py):
        if not rect:
            return False
        return (rect["x"] <= px <= rect["x"] + rect["w"]
                and rect["y"] <= py <= rect["y"] + rect["h"])

    def set_click_through(self, ignore):
        if self.ignore_state == ignore:
            return
        self.ignore_state = ignore
        plat.set_click_through(self.win, ignore)

    def track(self):
        if plat.OWNS_DRAG:
            return
        point, down = self.cursor()
        if point is None:
            self.hover = False
            return
        px, py = point[0] - self.x, point[1] - self.y
        over_robot = self._inside(self.regions["robot"], px, py)
        over_panel = self._inside(self.regions["panel"], px, py)
        over_extra = any(self._inside(r, px, py) for r in self.regions["extra"])
        self.hover = over_robot or over_panel or over_extra
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
                    plat.move_window(self.win, self.x, self.y)
                except Exception as exc:
                    guard("drag", exc)

        if self.hover or self.dragging:
            self.last_activity = time.time()
            self.sleeping = False
        elif time.time() - self.last_activity > LOOP_CFG.get("sleep_after_s", 180):
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

        plat.call_soon(act)

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
                    tick += 1
                    if tick % LOOP_CFG.get("push_every", 3) == 0:
                        self.push()
                    if tick % LOOP_CFG.get("heartbeat_every", 100) == 0:
                        log("alive tick=%d hover=%s drag=%s regions=%s"
                            % (tick, self.hover, self.dragging,
                               self.regions.get("robot")))
                    if tick % LOOP_CFG.get("quit_check_every", 10) == 0:
                        if self.win.evaluate_js("window.TIM && window.TIM.quit") is True:
                            log("quit flag seen")
                            os._exit(0)
            except Exception as exc:
                if tick % 100 == 0:
                    log("loop: %r" % exc)
            time.sleep(LOOP_CFG.get("tick_ms", 100) / 1000.0)

    def push(self):
        if not self.ready or self.win is None:
            return
        try:
            self.win.evaluate_js("window.TIM && window.TIM.state(%s)"
                                 % json.dumps({"hover": self.hover, "sleep": self.sleeping}))
        except Exception as exc:
            guard("push", exc)


def install_autostart():
    """Поднимает Т.И.М. при входе в систему средствами платформы."""
    if plat.install_autostart():
        log("autostart installed")
    else:
        log("autostart skipped", "warn")


def main():
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


def _run():
    bot = Bot()
    api = Api(bot)
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
