import os
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango

from . import envinfo, gitinfo
from .config import CONFIG_PATH, parse_accel
from .paths import IN_FLATPAK, bundled_data_dir, host_config_path_expr
from .tab import Tab

_CSS = b"""
.tab-bar {
    background: @headerbar_bg_color;
    border-bottom: 1px solid alpha(@borders, 0.5);
    padding: 1px 4px;
}
.tab-btn {
    min-height: 0;
    padding: 3px 4px 3px 8px;
    border-radius: 5px;
}
.tab-btn:hover {
    background: alpha(currentColor, 0.08);
}
/* where the tab you're dragging would land */
.tab-btn.drop-before {
    box-shadow: inset 2px 0 0 @accent_color;
}
.tab-btn.drop-after {
    box-shadow: inset -2px 0 0 @accent_color;
}
.tab-btn.active-tab {
    background: alpha(@accent_color, 0.18);
    color: @accent_color;
}
/* something in here rang while you were elsewhere, and stays lit until you look */
.tab-btn.belled-tab {
    background: alpha(@warning_color, 0.28);
    color: @warning_color;
    font-weight: bold;
}
.tab-close {
    min-height: 0;
    min-width: 0;
    padding: 2px;
}
"""


def _format_config_error(message):
    return f"\r\n\033[1;31mConfig error:\033[0m {message}\r\n\r\n"


_MAX_TAB_LABEL = 32
_LONG_COMMAND_SECONDS = 10
# you'll understand when you're older sweetie
_TORTURE_ICON = "elsevier"
_TORTURE_LABEL = "Article in Press"
# makes ssh detection work
_ENV_POLL_SECONDS = 2


def _collapse(head, parts, joiner):
    # compresses tabs so the middle goes first
    label = head + joiner + "/".join(parts)
    for drop in range(1, max(len(parts) - 1, 1)):
        if len(label) <= _MAX_TAB_LABEL:
            break
        label = head + joiner + "/".join([parts[0]] + [".."] * drop + parts[1 + drop :])
    return label


_icon_cache = {}


def _shipped_icon(slug):
    path = os.path.join(bundled_data_dir(), "icons", f"{slug}-symbolic.svg")
    if not os.path.exists(path):
        return None
    return Gio.FileIcon.new(Gio.File.new_for_path(path))


def _forge_icon(slug):
    # forge icons are included, git icon is because gnome sucks but it should fallback to a system one if availible
    if slug in _icon_cache:
        return _icon_cache[slug]

    icon = _shipped_icon(slug) if slug != gitinfo.GENERIC_FORGE else None
    if icon is None:
        display = Gdk.Display.get_default()
        theme = Gtk.IconTheme.get_for_display(display) if display else None
        names = [f"{slug}-symbolic", slug]
        if slug != gitinfo.GENERIC_FORGE:
            names += ["git-symbolic", "git"]
        for name in names:
            if theme and theme.has_icon(name):
                icon = Gio.ThemedIcon.new(name)
                break
    if icon is None:
        icon = _shipped_icon(gitinfo.GENERIC_FORGE)

    _icon_cache[slug] = icon
    return icon


def _themed_icon(slug, fallbacks):
    # same deal as before, fall back to the included one
    display = Gdk.Display.get_default()
    theme = Gtk.IconTheme.get_for_display(display) if display else None
    for name in fallbacks:
        if theme and theme.has_icon(name):
            return Gio.ThemedIcon.new(name)
    return _shipped_icon(slug)


def _env_icon(slug):
    if slug not in _icon_cache:
        if slug == "ssh":
            icon = _themed_icon(slug, ["network-server-symbolic"])
        else:
            icon = _shipped_icon(slug)
        _icon_cache[slug] = icon
    return _icon_cache[slug]


def _watch_dotgit(tab, path, refresh):
    # git init detection
    if tab.git_monitor:
        tab.git_monitor.cancel()
        tab.git_monitor = None
    try:
        monitor = Gio.File.new_for_path(os.path.join(path, ".git")).monitor_file(
            Gio.FileMonitorFlags.WATCH_MOVES, None
        )
    except GLib.Error:
        return
    monitor.connect("changed", lambda *_: refresh(path))
    tab.git_monitor = monitor


def _set_tab_state(tab, text, forge):
    tab.label = text
    tab._label_widget.set_label(text)
    icon = _forge_icon(forge) if forge else None
    if icon:
        tab._icon_widget.set_from_gicon(icon)
    tab._icon_widget.set_visible(icon is not None)


def _tab_tooltip(tab, remote_cwd, runtime):
    # to shorten tabs prn
    lines = [tab.label]
    if remote_cwd:
        lines.append(remote_cwd)
    if runtime:
        lines.append(runtime)
    return "\n".join(lines)


def _split_path(path, home):
    if path == home + "/" or path.startswith(home + "/"):
        return "~", [p for p in path[len(home) + 1 :].split("/") if p]
    return "", [p for p in path.lstrip("/").split("/") if p]


def _git_tab_label(path, info):
    rel = os.path.relpath(path, info.root)
    if rel == ".":
        return info.name
    return _collapse(info.name, [p for p in rel.split("/") if p], ": ")


def _tab_label_for_path(path, home):
    if path == home:
        # name from the host
        return f"Home ({os.path.basename(home)})" if os.path.basename(home) else "Home"
    root, parts = _split_path(path, home)
    if not parts:
        return root or "/"
    return _collapse(root, parts, "/")


# titlebar can fit more content
def _window_title(path, home, info):
    if info:
        rel = os.path.relpath(path, info.root)
        title = info.name if rel == "." else f"{info.name}: {rel}"
        # this is for git slop
        forge = gitinfo.FORGE_NAMES.get(info.forge)
        return f"{title} ({forge})" if forge else title
    if path == home:
        return "Jadeterm"
    root, parts = _split_path(path, home)
    if not parts:
        return root or "/"
    return root + "/" + "/".join(parts)


class Window(Gtk.ApplicationWindow):
    # more slop to make native titlebars work so this doesn't look like a libadw app
    # this get around the libadw version forcing a CSD
    def __init__(self, app, config, theme, bell):
        super().__init__(application=app)
        self._config = config
        self._torture = config.torture
        self._theme = theme
        self._bell = bell
        self._tabs = []
        self._active_tab = None

        self._set_window_title("Jadeterm")
        self.set_default_size(900, 600)

        self._load_css()
        self._build_ui()
        self._setup_accels(app)
        self.connect("notify::is-active", lambda *_: self._on_active_change())
        self._open_tab()

    def _set_window_title(self, text):
        if self._torture:
            text = f"[TORTURE MODE] {text} [TORTURE MODE]"
        self.set_title(text)

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

        self._bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._bar.add_css_class("tab-bar")
        root.append(self._bar)

        self._tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._bar.append(self._tab_bar)

        # the empty stretch is draggable, mostly for gnome
        # also the wm sloppers, hi tulip
        # the handle is like this so moving tabs doesnt move the window
        # i ran into this issue multiple times
        handle = Gtk.WindowHandle()
        handle.set_hexpand(True)
        handle.set_child(Gtk.Box())
        self._bar.append(handle)

        new_btn = Gtk.Button(icon_name="tab-new-symbolic")
        new_btn.add_css_class("flat")
        new_btn.set_tooltip_text("New tab")
        new_btn.connect("clicked", lambda _: self._open_tab())
        self._bar.append(new_btn)

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
        # prefer the host's $SHELL over the sandbox's
        shell = self._config.startup
        break_claude = self._config.break_claude
        home = os.path.expanduser("~")

        def on_exit(tab, _status):
            # prevents gtk from throwing a fit when closing tabs
            GLib.idle_add(self._close_tab, tab)

        def on_title(title):
            # for apps
            if command is not None and tab is self._active_tab and title:
                self._set_window_title(f"{title} — Jadeterm")

        def refresh(path):
            tab.cwd = path
            tab.cwd_remote = bool(tab.remote_host)
            self._apply_state(tab)

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
            tab.remote_host = envinfo.remote_host(uri)
            refresh(path)
            if tab.remote_host:
                if tab.git_monitor:
                    tab.git_monitor.cancel()
                    tab.git_monitor = None
            else:
                _watch_dotgit(tab, path, refresh)

        tab = Tab(
            shell=shell,
            break_claude=break_claude,
            theme=self._theme,
            on_bell=lambda: self._on_bell(tab),
            on_exit=on_exit,
            on_title_changed=on_title,
            # doesn't rename the config editor tab
            on_cwd_changed=on_cwd if command is None else None,
            on_command_finished=lambda: self._on_command_finished(tab),
            command=command,
            torture=self._torture,
            paywall_every=self._config.torture_paywall_every,
        )
        if label:
            tab.label = tab.base_label = label
        # this should drop errors on launch if the config is fucked
        # it might not, it's bad
        # this code is bad, i should fix it later
        if not self._tabs and self._config.error:
            tab.terminal.feed_error(_format_config_error(self._config.error))
        self._tabs.append(tab)
        self._stack.add_child(tab.terminal.widget())

        btn = self._make_tab_button(tab)
        self._tab_bar.append(btn)
        tab._btn = btn

        tab.terminal.connect_env_changed(lambda: self._on_env_report(tab))
        if not tab.shimmed:
            tab.env_poll = GLib.timeout_add_seconds(
                _ENV_POLL_SECONDS, self._poll_env, tab
            )

        self._switch_to(tab)
        self._sync_tabs()

    def _make_tab_button(self, tab):
        # this puts the tab close button in the tab
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        container.add_css_class("tab-btn")
        tab._tab_widget = container

        lbl = Gtk.Label(label=tab.label)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        # this is because of gnome again
        lbl.set_max_width_chars(_MAX_TAB_LABEL)
        tab._label_widget = lbl

        def small_image(gicon=None):
            image = Gtk.Image()
            image.set_pixel_size(14)
            if gicon:
                image.set_from_gicon(gicon)
            image.set_visible(False)
            container.append(image)
            return image

        tab._ssh_icon = small_image(_env_icon("ssh"))
        tab._container_icon = small_image(_env_icon(envinfo.OCI_ICON))
        tab._icon_widget = small_image()
        container.append(lbl)

        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("flat")
        close.add_css_class("tab-close")
        close.set_focusable(False)
        close.connect("clicked", lambda _: self._close_tab(tab))
        container.append(close)

        # tabs aren't buttons to prevent fuckiness
        # this is what i get for not using a platform library
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: tab in self._tabs and self._switch_to(tab))
        container.add_controller(click)

        self._make_draggable(tab, container)
        return container

    def _make_draggable(self, tab, container):
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect(
            "prepare",
            lambda *_: Gdk.ContentProvider.new_for_value(GObject.Value(str, tab.uid)),
        )
        source.connect(
            "drag-begin",
            lambda src, _drag: src.set_icon(
                Gtk.WidgetPaintable.new(container),
                container.get_width() // 2,
                container.get_height() // 2,
            ),
        )
        container.add_controller(source)

        def side(x):
            return "drop-after" if x > container.get_width() / 2 else "drop-before"

        def clear():
            container.remove_css_class("drop-before")
            container.remove_css_class("drop-after")

        def motion(_target, x, _y):
            clear()
            container.add_css_class(side(x))
            return Gdk.DragAction.MOVE

        def drop(_target, uid, x, _y):
            clear()
            dragged = next((t for t in self._tabs if t.uid == uid), None)
            if dragged is None or dragged is tab:
                return False
            index = self._tabs.index(tab) + (1 if side(x) == "drop-after" else 0)
            self._move_tab(dragged, index)
            return True

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("motion", motion)
        target.connect("leave", lambda *_: clear())
        target.connect("drop", drop)
        container.add_controller(target)

    def _move_tab(self, tab, index):
        old = self._tabs.index(tab)
        if index > old:
            index -= 1
        if index == old:
            return
        self._tabs.pop(old)
        self._tabs.insert(index, tab)
        self._tab_bar.remove(tab._btn)
        after = self._tabs[index - 1]._btn if index else None
        self._tab_bar.insert_child_after(tab._btn, after)

    def _apply_state(self, tab):
        home = os.path.expanduser("~")
        runtime, name = tab.terminal.container()
        container = bool(runtime or name) or tab.foreground == envinfo.CONTAINER
        # cleans up container name getting
        ssh = not container and (bool(tab.remote_host) or tab.foreground == envinfo.SSH)
        host = tab.remote_host or tab.target

        forge = ""
        if ssh:
            tab.base_label = f"SSH: {host}" if host else "SSH"
            tab.window_title = tab.base_label
        elif container:
            image = name or tab.target
            tab.base_label = f"Container: {image}" if image else "Container"
            tab.window_title = tab.base_label
        elif tab.cwd and not tab.cwd_remote:
            info = gitinfo.lookup(tab.cwd)
            if info:
                tab.base_label = _git_tab_label(tab.cwd, info)
                forge = info.forge
            else:
                tab.base_label = _tab_label_for_path(tab.cwd, home)
            tab.window_title = _window_title(tab.cwd, home, info)

        if self._torture:
            # this is so the torture icon trumps everything
            _set_tab_state(tab, f"{_TORTURE_LABEL}: {tab.base_label}", _TORTURE_ICON)
        else:
            _set_tab_state(tab, tab.base_label, forge)

        tab._ssh_icon.set_visible(ssh and not self._torture)
        if container:
            tab._container_icon.set_from_gicon(
                _env_icon(envinfo.container_icon(tab.report, runtime))
            )
        tab._container_icon.set_visible(container and not self._torture)
        remote_cwd = tab.cwd if ssh and tab.cwd_remote else ""
        tab._tab_widget.set_tooltip_text(_tab_tooltip(tab, remote_cwd, runtime))
        if tab is self._active_tab:
            self._set_window_title(tab.window_title)

    def _on_env_report(self, tab):
        # this makes me want to kill myself
        if tab.shimmed:
            self._take_report(tab, tab.terminal.foreground_report())
        self._apply_state(tab)

    def _poll_env(self, tab):
        if tab not in self._tabs:
            return False
        if self._take_report(tab, envinfo.local_foreground(tab.terminal.pty_fd())):
            self._apply_state(tab)
        return True

    def _take_report(self, tab, report):
        state = (envinfo.classify(report), envinfo.foreground_target(report), report)
        if state == (tab.foreground, tab.target, tab.report):
            return False
        tab.foreground, tab.target, tab.report = state
        return True

    def _watching(self, tab):
        return self.is_active() and tab is self._active_tab

    def _flag_bell(self, tab, pending):
        tab.bell_pending = pending
        if pending:
            tab._tab_widget.add_css_class("belled-tab")
        else:
            tab._tab_widget.remove_css_class("belled-tab")

    def _on_bell(self, tab):
        if self._watching(tab):
            return
        self._flag_bell(tab, True)
        self._bell.ring(tab.uid, tab.label)

    def _on_command_finished(self, tab):
        if not tab.command_started:
            return
        elapsed = (GLib.get_monotonic_time() - tab.command_started) / 1_000_000
        # so the y/n doesn't look like completion
        tab.command_started = 0
        # so short commands dont notify
        if elapsed < _LONG_COMMAND_SECONDS or self._watching(tab):
            return
        self._flag_bell(tab, True)
        self._bell.command_finished(tab.uid, tab.label, elapsed)

    def focus_tab(self, uid):
        for tab in self._tabs:
            if tab.uid == uid:
                self._switch_to(tab)
                break
        self.present()

    def _on_active_change(self):
        # if the tab is active dont send a notif
        if self.is_active() and self._active_tab:
            self._flag_bell(self._active_tab, False)

    def _switch_to(self, tab):
        if self._active_tab:
            self._active_tab._tab_widget.remove_css_class("active-tab")
        self._active_tab = tab
        self._flag_bell(tab, False)
        tab._tab_widget.add_css_class("active-tab")
        self._stack.set_visible_child(tab.terminal.widget())
        GLib.idle_add(tab.grab_focus)
        self._set_window_title(tab.window_title)

    def _close_tab(self, tab):
        if tab not in self._tabs:
            return False
        idx = self._tabs.index(tab)
        if tab.git_monitor:
            tab.git_monitor.cancel()
            tab.git_monitor = None
        if tab.env_poll:
            GLib.source_remove(tab.env_poll)
            tab.env_poll = 0
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
        return False  # glib idle shit

    def _close_active_tab(self):
        if self._active_tab:
            self._close_tab(self._active_tab)

    def _sync_tabs(self):
        # hides the tab bar if only one tab is open
        self._bar.set_visible(len(self._tabs) > 1)

    def apply_theme(self, theme):
        self._theme = theme
        for tab in self._tabs:
            tab.terminal.apply_theme(theme)

    def _reload_config(self):
        self._config.reload()
        # the tabs can be dressed up or undressed live, but the theatre itself lives
        # in the shim, so switching it only reaches tabs opened from here on
        self._torture = self._config.torture
        for tab in self._tabs:
            self._apply_state(tab)
        # reloading logic
        # doesn't restart shells
        # `startup` and `break-claude` only work on new tabs if you reload
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
