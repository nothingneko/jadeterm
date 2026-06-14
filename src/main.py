#!/usr/bin/env python3
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")
from gi.repository import Adw, Gio

from .bell import Bell
from .config import Config, parse_accel
from .paths import APP_ID
from .theme import Theme, load_theme
from .window import Window

# just in case somebody fucks up their system or the default config is missing for some reason
_EMERGENCY_PALETTE = {"base00": "#1e1e2e", "base05": "#cdd6f4"}


class Application(Adw.Application):
    # Adw.Application (not Adw.ApplicationWindow) this is so we can do libadw with a native window
    # i.e for plasma so i get my nice native titlebar
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self._config = None
        self._window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._config = Config()

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)

        if accel := parse_accel(self._config.keyboard("quit-app")):
            self.set_accels_for_action("app.quit", [accel])

    def do_activate(self):
        if self._window:
            self._window.present()
            return

        style_manager = Adw.StyleManager.get_default()
        self._apply_color_scheme(style_manager)
        theme = self._load_theme(style_manager)
        style_manager.connect("notify::dark", lambda sm, _: self._on_scheme_change(sm))

        self._window = Window(
            app=self,
            config=self._config,
            theme=theme,
            bell=Bell(self),
        )
        self._window.present()

    def _apply_color_scheme(self, style_manager):
        if self._config.prefer_dark:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def _load_theme(self, style_manager):
        is_dark = self._config.prefer_dark or style_manager.get_dark()
        name = self._config.dark_theme if is_dark else self._config.light_theme
        try:
            return load_theme(name)
        except FileNotFoundError:
            try:
                return load_theme("breeze-dark" if is_dark else "breeze")
            except FileNotFoundError:
                return Theme({"palette": _EMERGENCY_PALETTE})

    def _on_scheme_change(self, style_manager):
        # ignore xdg if the user has prefer dark
        if self._config.prefer_dark:
            return
        self._push_theme(style_manager)

    def reload_theme(self):
        style_manager = Adw.StyleManager.get_default()
        self._apply_color_scheme(style_manager)
        self._push_theme(style_manager)

    def _push_theme(self, style_manager):
        theme = self._load_theme(style_manager)
        if self._window:
            self._window.apply_theme(theme)


def main():
    app = Application()
    return app.run(sys.argv)
