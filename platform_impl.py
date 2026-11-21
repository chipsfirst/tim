"""Выбор платформенной реализации: mac_backend или win_backend."""

import sys

NAMES = ("setup", "work_area", "cursor", "move_window", "set_click_through",
         "start_drag", "start_tray", "start_hotkey", "install_autostart",
         "call_soon", "OWNS_DRAG",
         "autostart_enabled", "set_autostart")

if sys.platform == "win32":
    from win_backend import (setup, work_area, cursor, move_window,
                             set_click_through, start_drag, start_tray,
                             start_hotkey, install_autostart,
                             call_soon, OWNS_DRAG,
                             autostart_enabled, set_autostart)
else:
    from mac_backend import (setup, work_area, cursor, move_window,
                             set_click_through, start_drag, start_tray,
                             start_hotkey, install_autostart,
                             call_soon, OWNS_DRAG,
                             autostart_enabled, set_autostart)

__all__ = list(NAMES)
