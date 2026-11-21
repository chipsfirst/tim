"""Дымовые проверки Т.И.М.: то, что ломалось руками, теперь проверяется само."""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class RegionsTest(unittest.TestCase):
    """Попадание курсора в зоны робота, панели и меню."""

    def test_inside_rect(self):
        rect = {"x": 100, "y": 50, "w": 40, "h": 20}
        self.assertTrue(main.Bot._inside(rect, 100, 50))
        self.assertTrue(main.Bot._inside(rect, 140, 70))
        self.assertFalse(main.Bot._inside(rect, 99, 50))
        self.assertFalse(main.Bot._inside(rect, 141, 70))

    def test_empty_region(self):
        self.assertFalse(main.Bot._inside(None, 10, 10))
        self.assertFalse(main.Bot._inside({}, 10, 10))


class PlatformTest(unittest.TestCase):
    def test_interface_complete(self):
        import platform_impl as plat

        for name in ("setup", "work_area", "cursor", "move_window",
                     "set_click_through", "start_drag", "start_tray",
                     "start_hotkey", "install_autostart", "call_soon"):
            self.assertTrue(callable(getattr(plat, name, None)), name)
        self.assertIsInstance(plat.OWNS_DRAG, bool)

    def test_cursor_returns_pair(self):
        import platform_impl as plat

        point, down = plat.cursor()
        self.assertIsInstance(down, bool)
        if point is not None:
            self.assertEqual(len(point), 2)


class SilenceTest(unittest.TestCase):
    """Раньше ошибки глотались молча — из-за этого полдня искали причины."""

    def test_no_silent_except(self):
        for rel in ("main.py", "mac_backend.py", "win_backend.py"):
            source = read(rel)
            bad = re.findall(r"except Exception as exc:\s*\n\s+pass", source)
            self.assertEqual(bad, [], "%s: исключение поймано и забыто" % rel)


class ConfigTest(unittest.TestCase):
    def test_config_complete(self):
        import json

        cfg = json.loads(read("ui/config.json"))
        for section in ("window", "loop", "stats", "humor", "hunger"):
            self.assertIn(section, cfg)
        self.assertGreater(cfg["window"]["width"], 200)
        self.assertGreater(cfg["stats"]["tick_ms"], 1000)

    def test_python_uses_config(self):
        self.assertEqual(main.WIN_W, 300)
        self.assertEqual(main.LOOP_CFG.get("tick_ms"), 100)


class AliceTest(unittest.TestCase):
    def test_read_limit(self):
        self.assertIn("t.slice(0, 10000)", main.READ_JS)

    def test_echo_guard_present(self):
        src = read("main.py")
        self.assertIn("echo = now.strip().lower().startswith(probe)", src,
                      "ответ-эхо снова может попасть в интерфейс")

    def test_answer_logged(self):
        self.assertIn("answer: %d chars", read("main.py"))


class MenuTest(unittest.TestCase):
    """Пункты меню объявлены в реестре и все ведут на вызываемый код."""

    def test_actions_have_handlers(self):
        app = read("ui/app.js")
        block = app[app.index("TIM.menu.mount(["):app.index("]);", app.index("TIM.menu.mount(["))]
        ids = re.findall(r'id: "([a-z]+)"', block)
        for required in ("feed", "dance", "weather", "joke", "games", "more"):
            self.assertIn(required, ids)
        self.assertEqual(block.count("run:") + block.count("items:"), block.count('id: "'))

    def test_nested_groups(self):
        app = read("ui/app.js")
        self.assertIn('label: "Игры ▸"', app)
        self.assertIn('label: "Сервис ▸"', app)
        self.assertIn('label: "Настройки ▸"', app)
        block = app[app.index('label: "Сервис ▸"'):]
        self.assertIn('id: "reset"', block)

    def test_menu_script_exists(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, "ui/js/menu.js")))
        self.assertNotIn("<script>", read("ui/index.html"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
