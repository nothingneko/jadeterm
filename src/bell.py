from gi.repository import Gio, GLib


def _duration(seconds):
    if seconds < 60:
        return f"{round(seconds)}s"
    minutes, seconds = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


class Bell:
    def __init__(self, app):
        self._app = app

    def _send(self, kind, tab_id, title, body):
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_priority(Gio.NotificationPriority.NORMAL)
        # open the tab that sent the bell
        notification.set_default_action_and_target(
            "app.focus-tab", GLib.Variant("s", tab_id)
        )
        # one id PER TAB so two tabs can send you notifs, also they just replace the last one it's a terminal you don't need every notif ever
        self._app.send_notification(f"{kind}-{tab_id}", notification)

    def ring(self, tab_id, label):
        self._send("bell", tab_id, "Terminal Bell", label)

    def command_finished(self, tab_id, label, seconds):
        # vte hates me and always returns 0, thanks gnome
        self._send(
            "command", tab_id, "Command finished", f"{label} · {_duration(seconds)}"
        )
