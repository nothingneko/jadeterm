import os

import gi

gi.require_version("Vte", "3.91")
from gi.repository import Gdk, GLib, Gtk, Vte

from .envinfo import FOREGROUND_TERMPROP

# vte drops termprops it was never told about, so ours has to be declared up front
Vte.install_termprop(
    FOREGROUND_TERMPROP, Vte.PropertyType.STRING, Vte.PropertyFlags.NONE
)

# this is so when you backspace it doesnt send the bell notification
# because it was pissing me off like crazy
# no you cannot disable the bell piss off
#
# p.s. if you press backspace within 200ms of a bell it won't play
_REJECT_KEYS = frozenset((Gdk.KEY_BackSpace, Gdk.KEY_Delete))
_REJECT_BELL_WINDOW_US = 200_000


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

        self._last_reject_key = 0
        self._saw_postexec = False

        if bell_handler:
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self._note_reject_key)
            self._vte.add_controller(keys)
            self._vte.connect("bell", lambda _: self._ring(bell_handler))

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_child(self._vte)
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_vexpand(True)
        self._scroll.set_hexpand(True)

    def _note_reject_key(self, _controller, keyval, _keycode, _state):
        if keyval in _REJECT_KEYS:
            self._last_reject_key = GLib.get_monotonic_time()
        return False

    def _ring(self, handler):
        since = GLib.get_monotonic_time() - self._last_reject_key
        if since < _REJECT_BELL_WINDOW_US:
            return
        handler()

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

    def connect_command_boundaries(self, on_submit, on_done):
        # this is because vte is bad and doesn't tell me when a command starts
        def committed(_vte, text, _length):
            if "\r" in text or "\n" in text:
                on_submit()

        self._vte.connect("commit", committed)

        # more vte/zsh slop
        # i could not fucking figure out why this didn't work, claude didn't either for like an hour
        # pro tip: tell claude "go my chudling" and it'll work better, that's how i made it solve this
        # pro tip #2: even though it "solved" this after i called it a chudling it didn't actualy and i spent another hour figuring it out
        def changed(_vte, name):
            if name == Vte.TERMPROP_SHELL_POSTEXEC:
                self._saw_postexec = True
                on_done()
            elif name == Vte.TERMPROP_SHELL_PRECMD and not self._saw_postexec:
                on_done()

        self._vte.connect("termprop-changed", changed)

    def connect_env_changed(self, callback):
        watched = (
            Vte.TERMPROP_CONTAINER_RUNTIME,
            Vte.TERMPROP_CONTAINER_NAME,
            FOREGROUND_TERMPROP,
        )

        def changed(_vte, name):
            if name in watched:
                callback()

        self._vte.connect("termprop-changed", changed)

    def foreground_report(self):
        report, _ = self._vte.get_termprop_string(FOREGROUND_TERMPROP)
        return report or ""

    def container(self):
        # container detection
        runtime, _ = self._vte.get_termprop_string(Vte.TERMPROP_CONTAINER_RUNTIME)
        name, _ = self._vte.get_termprop_string(Vte.TERMPROP_CONTAINER_NAME)
        return (runtime or "", name or "")

    def pty_fd(self):
        pty = self._vte.get_pty()
        return pty.get_fd() if pty else -1

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
