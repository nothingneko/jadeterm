import os
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .config import CONFIG_PATH, parse_accel
from .paths import host_config_path_expr
from .tab import Tab

_CSS = b"""
.tab-bar {
    background: @headerbar_bg_color;
    border-bottom: 1px solid alpha(@borders, 0.5);
    padding: 1px 4px;
}
.tab-btn {
    min-height: 0;
    padding: 2px 4px 2px 8px;
    border-radius: 5px;
}
.tab-btn.active-tab {
    background: alpha(@accent_color, 0.18);
    color: @accent_color;
}
.tab-label-btn {
    min-height: 0;
    padding: 0;
}
.tab-close {
    min-height: 0;
    min-width: 0;
    padding: 2px;
}
"""


def _format_config_error(message):
    return f"\r\n\033[1;31mConfig error:\033[0m {message}\r\n\r\n"


class Window(Gtk.ApplicationWindow):
    # more slop to make native titlebars work so this doesn't look like a libadw app
    # this get around the libadw version forcing a CSD
    def __init__(self, app, config, theme, bell):
        super().__init__(application=app)
        self._config = config
        self._theme = theme
        self._bell = bell
        self._tabs = []
        self._active_tab = None

        self.set_title("Jadeterm")
        self.set_default_size(900, 600)

        self._load_css()
        self._build_ui()
        self._setup_accels(app)
        self._open_tab()

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.add_css_class("tab-bar")

        # this makes the tab bar draggable, mostly for gnome
        # also the wm sloppers, hi tulip
        self._handle = Gtk.WindowHandle()
        self._handle.set_child(bar)
        root.append(self._handle)

        self._tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        bar.append(self._tab_bar)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        new_btn = Gtk.Button(icon_name="tab-new-symbolic")
        new_btn.add_css_class("flat")
        new_btn.set_tooltip_text("New tab")
        new_btn.connect("clicked", lambda _: self._open_tab())
        bar.append(new_btn)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self._stack.set_vexpand(True)
        self._stack.set_hexpand(True)
        root.append(self._stack)

    def _setup_accels(self, app):
        actions = (
            ("new-tab", self._open_tab),
            ("close-tab", self._close_active_tab),
            ("reload-config", self._reload_config),
            ("edit-config", self._open_editor_tab),
            (
                "copy",
                lambda: self._active_tab and self._active_tab.terminal.copy_selection(),
            ),
            ("paste", lambda: self._active_tab and self._active_tab.terminal.paste()),
        )
        for name, handler in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_, h=handler: h())
            self.add_action(action)

        # this is for configurable keyboard shortcuts
        for cfg_key in ("new-tab", "close-tab"):
            if accel := parse_accel(self._config.keyboard(cfg_key)):
                app.set_accels_for_action(f"win.{cfg_key}", [accel])

        # these are hardcoded, you can change them in a fork, if you fork to do that please kindly shove a melonballer... somewhere
        # shift+comma sends the less symbol on some layouts and it gets fucky
        # this also fixes copy paste because VTE hates me
        fixed = {
            "win.reload-config": ["<Control><Shift>comma", "<Control><Shift>less"],
            "win.edit-config": ["<Control>comma"],
            "win.copy": ["<Control><Shift>c"],
            "win.paste": ["<Control><Shift>v"],
        }
        for name, accels in fixed.items():
            app.set_accels_for_action(name, accels)

    def _open_tab(self, command=None, label=None):
        # prefer the host's $SHELL over the sandbox's /bin/sh in flatpak
        shell = self._config.startup
        break_claude = self._config.break_claude
        home = os.path.expanduser("~")

        def on_exit(tab, _status):
            # prevents gtk from throwing a fit when we close tabs
            GLib.idle_add(self._close_tab, tab)

        def on_title(title):
            if tab is self._active_tab and title:
                self.set_title(f"{title} — Jadeterm")

        def on_cwd(uri):
            # this makes the tabs change cleanly outside of fish
            # if you're using fish congrats you don't need this part
            # but also you're using fish so what beyond this is going well in your life
            if not uri:
                return
            try:
                path = unquote(urlparse(uri).path)
            except Exception:
                return
            if path == home:
                new_label = "~"
            elif path.startswith(home + "/"):
                new_label = "~/" + os.path.basename(path)
            else:
                new_label = os.path.basename(path) or path
            tab._label_widget.set_label(new_label)

        tab = Tab(
            shell=shell,
            break_claude=break_claude,
            theme=self._theme,
            bell=self._bell,
            on_exit=on_exit,
            on_title_changed=on_title,
            # doesn't rename the config editor tab
            on_cwd_changed=on_cwd if command is None else None,
            command=command,
        )
        if label:
            tab.label = label
        # this should drop errors on launch if the config is fucked
        # it might not, it's bad
        if not self._tabs and self._config.error:
            tab.terminal.feed_error(_format_config_error(self._config.error))
        self._tabs.append(tab)
        self._stack.add_child(tab.terminal.widget())

        btn = self._make_tab_button(tab)
        self._tab_bar.append(btn)
        tab._btn = btn

        self._switch_to(tab)
        self._sync_tabs()

    def _make_tab_button(self, tab):
        # this puts the tab close button in the tab
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        container.add_css_class("tab-btn")
        tab._tab_widget = container

        lbl = Gtk.Label(label=tab.label)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_max_width_chars(14)
        tab._label_widget = lbl

        switch_btn = Gtk.Button()
        switch_btn.set_child(lbl)
        switch_btn.add_css_class("flat")
        switch_btn.add_css_class("tab-label-btn")
        switch_btn.connect("clicked", lambda _: self._switch_to(tab))
        container.append(switch_btn)

        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("flat")
        close.add_css_class("tab-close")
        close.set_focusable(False)
        close.connect("clicked", lambda _: self._close_tab(tab))
        container.append(close)

        return container

    def _switch_to(self, tab):
        if self._active_tab:
            self._active_tab._tab_widget.remove_css_class("active-tab")
        self._active_tab = tab
        tab._tab_widget.add_css_class("active-tab")
        self._stack.set_visible_child(tab.terminal.widget())
        GLib.idle_add(tab.grab_focus)
        self.set_title("Jadeterm")

    def _close_tab(self, tab):
        if tab not in self._tabs:
            return False
        idx = self._tabs.index(tab)
        self._tabs.remove(tab)
        self._tab_bar.remove(tab._btn)
        self._stack.remove(tab.terminal.widget())

        if not self._tabs:
            self.close()
            return False

        if self._active_tab is tab:
            self._active_tab = None
            self._switch_to(self._tabs[min(idx, len(self._tabs) - 1)])

        self._sync_tabs()
        return False  # required by GLib.idle_add to not repeat

    def _close_active_tab(self):
        if self._active_tab:
            self._close_tab(self._active_tab)

    def _sync_tabs(self):
        # hides the tab bar if only one tab is open
        self._handle.set_visible(len(self._tabs) > 1)

    def apply_theme(self, theme):
        self._theme = theme
        for tab in self._tabs:
            tab.terminal.apply_theme(theme)

    def _reload_config(self):
        self._config.reload()
        # reloading logic
        # doesn't restart shells
        # `startup` and `break-claude` only effect for newly opened tabs if you reload
        self._setup_accels(self.get_application())
        self.get_application().reload_theme()
        if self._config.error and self._active_tab:
            self._active_tab.terminal.feed_error(
                _format_config_error(self._config.error)
            )

    def _open_editor_tab(self):
        # touch the file and dir so bad editors don't break
        # i am finally throwing a bone to nano users
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        if not os.path.exists(CONFIG_PATH):
            open(CONFIG_PATH, "a").close()

        # this is so $EDITOR can still be grabbed in the flatpak
        command = ["sh", "-c", f'exec ${{EDITOR:-nano}} "{host_config_path_expr()}"']
        self._open_tab(command=command, label="config.yaml")
