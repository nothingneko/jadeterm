import os

APP_ID = "sh.jaiden.Jadeterm"
IN_FLATPAK = os.path.exists("/.flatpak-info")

_FLATPAK_DATA_DIR = "/app/share/jadeterm"


def bundled_data_dir():
    if os.path.isdir(_FLATPAK_DATA_DIR):
        return _FLATPAK_DATA_DIR
    # this is for pip slop while i'm building this
    # claude fixed this like 4 times because i suck at pip and python devenv stuff
    # don't ask me how it works because 5 guides and claude explaining it over and over could not teach me
    here = os.path.abspath(__file__)
    for _ in range(6):
        here = os.path.dirname(here)
        candidate = os.path.join(here, "data")
        if os.path.isdir(candidate):
            return candidate
    return _FLATPAK_DATA_DIR


def user_config_dir():
    # for that flatpak, keeps shit in the appdirs
    # removing cleans up user data.
    if IN_FLATPAK:
        return os.path.expanduser(f"~/.var/app/{APP_ID}/config/jadeterm")
    return os.path.expanduser("~/.config/jadeterm")


def host_config_path_expr():
    # `$HOME` is resolved by the shell, this is because i am lazy and it works well
    # this happens in flatpak and on the host
    if IN_FLATPAK:
        return f"$HOME/.var/app/{APP_ID}/config/jadeterm/config.yaml"
    return "$HOME/.config/jadeterm/config.yaml"
