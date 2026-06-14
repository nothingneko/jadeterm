import os

import gi

gi.require_version("Gdk", "4.0")
import yaml
from gi.repository import Gdk

from .paths import bundled_data_dir, user_config_dir

_BUNDLED_THEME_DIR = os.path.join(bundled_data_dir(), "themes")
_USER_THEME_DIR = os.path.join(user_config_dir(), "themes")

# yes my themes are yaml, no you cannot kill me in a backalley
# base16 slot → VTE 16-color palette index
_PALETTE_MAP = [
    "base00",
    "base08",
    "base0B",
    "base0A",
    "base0D",
    "base0E",
    "base0C",
    "base05",
    "base03",
    "base08",
    "base0B",
    "base0A",
    "base0D",
    "base0E",
    "base0C",
    "base07",
]


def _rgba(hex_color):
    c = Gdk.RGBA()
    c.parse(hex_color)
    return c


class Theme:
    def __init__(self, data):
        self.name = data.get("name", "Unknown")
        raw = data.get("palette", {})
        self.palette = {k: _rgba(v) for k, v in raw.items()}

    @property
    def background(self):
        return self.palette.get("base00", _rgba("#000000"))

    @property
    def foreground(self):
        return self.palette.get("base05", _rgba("#ffffff"))

    def color_palette(self):
        return [self.palette.get(k, _rgba("#000000")) for k in _PALETTE_MAP]


def load_theme(name):
    # user themes live in ~/.config/jadeterm/themes/* (or the flatpak appdir),
    # if they conflict a bundled one the user one wins
    # why? i dont know this just makes sense, nobody else is gonna make a theme called "hec"
    for d in (_USER_THEME_DIR, _BUNDLED_THEME_DIR):
        path = os.path.join(d, f"{name}.yaml")
        if os.path.exists(path):
            with open(path) as f:
                return Theme(yaml.safe_load(f))
    raise FileNotFoundError(
        f"Theme '{name}' not found in {_USER_THEME_DIR} or {_BUNDLED_THEME_DIR}"
    )
