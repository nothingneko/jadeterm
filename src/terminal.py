import os

import gi

gi.require_version("Vte", "3.91")
from gi.repository import GLib, Gtk, Vte


class Terminal:
    def __init__(self, bell_handler=None):
        self._vte = Vte.Terminal()
        self._vte.set_scrollback_lines(10000)
        self._vte.set_scroll_on_output(
            False
        )  # don't go to the bottom when reading scrollback, yes i encountered this bug
        self._vte.set_scroll_on_keystroke(True)
        self._vte.set_mouse_autohide(True)
        self._vte.set_allow_hyperlink(True)

        if bell_handler:
            self._vte.connect("bell", lambda _: bell_handler())

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_child(self._vte)
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_vexpand(True)
        self._scroll.set_hexpand(True)

    def widget(self):
        return self._scroll

    def grab_focus(self):
        self._vte.grab_focus()

    def apply_theme(self, theme):
        self._vte.set_color_background(theme.background)
        self._vte.set_color_foreground(theme.foreground)
        self._vte.set_colors(theme.foreground, theme.background, theme.color_palette())

    def connect_title_changed(self, callback):
        self._vte.connect(
            "window-title-changed", lambda vte: callback(vte.get_window_title() or "")
        )

    def connect_cwd_changed(self, callback):
        self._vte.connect(
            "notify::current-directory-uri",
            lambda vte, _: callback(vte.get_current_directory_uri() or ""),
        )

    def connect_child_exited(self, callback):
        self._vte.connect("child-exited", lambda vte, status: callback(status))

    def feed_error(self, text):
        self._vte.feed(text.encode())

    def copy_selection(self):
        self._vte.copy_clipboard_format(Vte.Format.TEXT)

    def paste(self):
        self._vte.paste_clipboard()

    def spawn_async(self, argv, env_list=None):
        def cb(terminal, pid, error, user_data=None):
            pass

        self._vte.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.path.expanduser(
                "~"
            ),  # always start in home, why? i don't like when it doesn't
            argv,
            env_list,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            cb,
            None,
        )
