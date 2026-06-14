import os

import yaml

from .paths import bundled_data_dir, user_config_dir

CONFIG_PATH = os.path.join(user_config_dir(), "config.yaml")
_DEFAULTS_PATH = os.path.join(bundled_data_dir(), "default-config.yaml")

_TRUTHY = ("enabled", "true", "yes", "1")
_FALSY = ("disabled", "false", "no", "0")
_BOOLISH_STRINGS = _TRUTHY + _FALSY


def _truthy(val):
    return str(val).lower() in _TRUTHY


class ConfigError(Exception):
    pass


def _type_name(value):
    if isinstance(value, bool):  # bool is a subclass of int
        return "boolean"
    return {
        str: "string",
        int: "number",
        float: "number",
        list: "list",
        dict: "mapping",
        type(None): "null",
    }.get(type(value), type(value).__name__)


def _validate(value, default, path):
    if value is None:
        return  # empty conf means keep the defaults
    if isinstance(default, dict):
        if not isinstance(value, dict):
            raise ConfigError(
                f"'{path or 'top level'}' must be a mapping, i have {_type_name(value)}"
            )
        for key, val in value.items():
            cur_path = f"{path}.{key}" if path else key
            if key in default:
                _validate(val, default[key], cur_path)
            # ignores unknown keys
    elif isinstance(default, bool) or (
        isinstance(default, str) and default.lower() in _BOOLISH_STRINGS
    ):
        # accept yaml bool or yes/no/true/false
        if not isinstance(value, (bool, str)):
            raise ConfigError(
                f"'{path}' must be a boolean (yes/no/true/false), i have {_type_name(value)}"
            )
    elif isinstance(default, str):
        if not isinstance(value, str):
            raise ConfigError(f"'{path}' must be a string, i have {_type_name(value)}")
    elif default is None:
        # (e.g. startup) accept a string or nothing
        if not isinstance(value, str):
            raise ConfigError(
                f"'{path}' must be a string or nothing, i have {_type_name(value)}"
            )


def _deep_merge(base, override):
    # types are checked separately via _validate.
    result = dict(base)
    for key, val in override.items():
        default_is_section = key in result and isinstance(result[key], dict)
        if default_is_section and val is None:
            continue
        if default_is_section and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _load_defaults():
    # if the default conf is missing this happens, some packager somewhere fucked up
    if not os.path.exists(_DEFAULTS_PATH):
        raise FileNotFoundError(
            f"bundled default config missing: {_DEFAULTS_PATH} ask the package maintainer for your distro to fix this, or get with the times and use the flatpak, unless you deleted it, then put it back!"
        )
    with open(_DEFAULTS_PATH) as f:
        return yaml.safe_load(f) or {}


DEFAULTS = _load_defaults()


def parse_accel(shortcut):
    if not isinstance(shortcut, str) or not shortcut:
        return None
    parts = shortcut.lower().split("+")
    key = parts[-1]
    mods = []
    for m in parts[:-1]:
        if m == "ctrl":
            mods.append("<Control>")
        elif m == "shift":
            mods.append("<Shift>")
        elif m == "alt":
            mods.append("<Alt>")
        elif m == "super":
            mods.append("<Super>")
    return "".join(mods) + (key.capitalize() if len(key) > 1 else key)


class Config:
    def __init__(self):
        self.error = None
        self._data = _deep_merge(DEFAULTS, {})
        self._load()

    def _load(self):
        # defaults stay in self.data unless user config loads properly, fall back if it doesn't
        self.error = None
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH) as f:
                user_data = yaml.safe_load(f) or {}
            _validate(user_data, DEFAULTS, "")
            self._data = _deep_merge(DEFAULTS, user_data)
        except (ConfigError, yaml.YAMLError, OSError) as e:
            self.error = str(e)
            self._data = _deep_merge(DEFAULTS, {})  # back to defaults

    def reload(self):
        self._load()

    @property
    def break_claude(self):
        return _truthy(self._data["integration"]["break-claude"])

    @property
    def prefer_dark(self):
        return _truthy(self._data["integration"]["prefer-dark"])

    @property
    def light_theme(self):
        return self._data["theme"]["light"]

    @property
    def dark_theme(self):
        return self._data["theme"]["dark"]

    @property
    def startup(self):
        return self._data.get("startup")

    def keyboard(self, action):
        return self._data["keyboard"].get(action)
