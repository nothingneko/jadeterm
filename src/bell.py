from gi.repository import Gio


class Bell:
    def __init__(self, app):
        self._app = app
        # one ID, replaces the previous one rather than stacking multiple notifications
        self._notification = Gio.Notification.new("Terminal Bell")
        self._notification.set_priority(Gio.NotificationPriority.NORMAL)

    def ring(self):
        self._app.send_notification("bell", self._notification)
