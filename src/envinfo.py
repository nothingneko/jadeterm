import os
import socket
import subprocess
from urllib.parse import urlparse

from .paths import IN_FLATPAK

SSH = "ssh"
CONTAINER = "container"

# this is so the host can send data into the sandbox
FOREGROUND_TERMPROP = "vte.ext.jadeterm.foreground"

# this detects the things that put you into shells elsewhere
_SSH_COMMANDS = frozenset(("ssh", "autossh", "sshpass", "mosh-client", "et"))
_CONTAINER_COMMANDS = frozenset(
    (
        "toolbox",
        "distrobox",
        "distrobox-enter",
        "lxc",
        "incus",
        "nsenter",
        "systemd-nspawn",
        "machinectl",
    )
)

# this is so we don't get the tab changing when we just do ps or such
_ENGINE_COMMANDS = frozenset(("podman", "podman-remote", "docker", "nerdctl", "ctr"))
_ENGINE_ATTACHING = frozenset(("run", "exec", "attach", "start"))

# decides what icon to use
OCI_ICON = "opencontainersinitiative"
_ICONS = {
    "containerd": "containerd",
    "ctr": "containerd",
    "nerdctl": "containerd",
    "incus": "linuxcontainers",
    "lxc": "linuxcontainers",
    "lxd": "linuxcontainers",
}

# this is really fucking nasty but it works and i came up with it so im proud of it a little
#   -B bind_interface   -b bind_address   -c cipher_spec   -D [addr:]port
#   -E log_file         -e escape_char    -F configfile    -I pkcs11
#   -i identity_file    -J destination    -L local_forward -l login_name
#   -m mac_spec         -O ctl_cmd        -o option        -p port
#   -Q query_option     -R remote_forward -S ctl_path      -W host:port
#   -w local_tun
_SSH_VALUE_FLAGS = frozenset("B b c D E e F I i J L l m O o p Q R S W w".split())

# this also
_ENGINE_VALUE_FLAGS = frozenset("v e p u w a".split())
_ENGINE_VALUE_OPTIONS = frozenset(
    (
        "--name",
        "--env",
        "--volume",
        "--publish",
        "--user",
        "--workdir",
        "--entrypoint",
        "--network",
        "--hostname",
        "--label",
        "--mount",
        "--device",
        "--pod",
    )
)

_local_hosts = {"localhost", "localhost.localdomain"}
_asked_host = False


def _learn(name):
    name = (name or "").strip().lower()
    if name:
        _local_hosts.add(name)
        _local_hosts.add(name.split(".")[0])


_learn(socket.gethostname())


def _learn_host_hostname():
    # this is to avoid the sandbox causing issues
    global _asked_host
    if _asked_host:
        return
    _asked_host = True
    try:
        result = subprocess.run(
            ["flatpak-spawn", "--host", "sh", "-c", "cat /etc/hostname || hostname"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return
    for line in result.stdout.splitlines():
        _learn(line)


def remote_host(uri):
    # more double checking
    try:
        host = (urlparse(uri).hostname or "").lower()
    except ValueError:
        return ""
    if not host:
        return ""
    if IN_FLATPAK:
        _learn_host_hostname()
    if host in _local_hosts:
        return ""
    return host


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _parse(report):
    command, _, rest = report.partition(":")
    return command, rest.split()


def _positionals(command, args):
    if command in _SSH_COMMANDS:
        flags, options = _SSH_VALUE_FLAGS, frozenset()
    else:
        flags, options = _ENGINE_VALUE_FLAGS, _ENGINE_VALUE_OPTIONS
    found = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg.startswith("-"):
            skip = arg in options or (len(arg) == 2 and arg[1] in flags)
            continue
        found.append(arg)
    return found


def classify(report):
    command, args = _parse(report)
    if command in _SSH_COMMANDS:
        return SSH
    if command in _CONTAINER_COMMANDS:
        return CONTAINER
    if command not in _ENGINE_COMMANDS:
        return ""
    subcommand = _positionals(command, args)[:1]
    return CONTAINER if subcommand and subcommand[0] in _ENGINE_ATTACHING else ""


def foreground_target(report):
    command, args = _parse(report)
    positionals = _positionals(command, args)
    if command in _SSH_COMMANDS:
        return positionals[0].rpartition("@")[2] if positionals else ""
    return positionals[1] if len(positionals) > 1 else ""


def container_icon(report, runtime):
    command, _ = _parse(report)
    return _ICONS.get(command) or _ICONS.get(runtime.lower()) or OCI_ICON


def local_foreground(pty_fd):
    # fixes sandbox pty fuckery
    if IN_FLATPAK or pty_fd is None or pty_fd < 0:
        return ""
    try:
        pgid = os.tcgetpgrp(pty_fd)
    except OSError:
        return ""
    if pgid <= 0:
        return ""
    command = _read(f"/proc/{pgid}/comm").strip()
    if not command:
        return ""
    args = [a for a in _read(f"/proc/{pgid}/cmdline").split("\0") if a][1:]
    return f"{command}:{' '.join(args)}" if args else command
