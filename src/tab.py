import os
import sys

from gi.repository import GLib

from .envinfo import FOREGROUND_TERMPROP
from .paths import IN_FLATPAK
from .terminal import Terminal
from .torture import PAYWALL_EVERY

# this is because flatpak-spawn isn't designed to do this, this is a fucking mess
# every time i need to work with this shit i question why i did this like that
# it does work so whatever
_PTY_SHIM = """
import fcntl, os, pty, select, signal, struct, sys, termios, time, tty

POLL_SECONDS = 0.1
FOREGROUND_SECONDS = 1

pid, master = pty.fork()
if pid == 0:
    os.execvp(sys.argv[1], sys.argv[1:])

size = None
foreground = None
foreground_due = 0

@TORTURE@

def read_proc(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""

def report_foreground():
    # sandbox moments
    global foreground, foreground_due
    now = time.monotonic()
    if now < foreground_due:
        return
    foreground_due = now + FOREGROUND_SECONDS
    try:
        pgid = os.tcgetpgrp(master)
    except OSError:
        return
    if pgid <= 0:
        return
    command = read_proc("/proc/%d/comm" % pgid).strip()
    args = [a for a in read_proc("/proc/%d/cmdline" % pgid).split("\\0") if a][1:]
    report = command + ":" + " ".join(args) if args else command
    report = "".join(c for c in report if c.isalnum() or c in "-_./@: ")[:128]
    if report != foreground:
        foreground = report
        os.write(1, b"\\033]666;@PROP@=" + report.encode() + b"\\033\\\\")

def resize(*_):
    global size
    try:
        current = fcntl.ioctl(0, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
    except OSError:
        return
    if current == size:
        return
    try:
        fcntl.ioctl(master, termios.TIOCSWINSZ, current)
    except OSError:
        return
    size = current

signal.signal(signal.SIGWINCH, resize)
resize()

try:
    saved = termios.tcgetattr(0)
    tty.setraw(0)
except termios.error:
    saved = None

try:
    while True:
        try:
            readable, _, _ = select.select([0, master], [], [], POLL_SECONDS)
        except InterruptedError:
            continue
        resize()
        report_foreground()
        now = time.monotonic()
        pending = theater.tick(now)
        if pending:
            os.write(1, pending)
        if master in readable:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            shown = theater.child_output(data, now)
            if shown:
                os.write(1, shown)
        if 0 in readable:
            data = os.read(0, 65536)
            if not data:
                break
            announced = theater.saw_input(data, now)
            if announced:
                os.write(1, announced)
            os.write(master, data)
finally:
    os.write(1, theater.flush())
    if saved is not None:
        termios.tcsetattr(0, termios.TCSAFLUSH, saved)

raise SystemExit(os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]))
""".replace("@PROP@", FOREGROUND_TERMPROP)


def _torture_source():
    # nasty nasty nasty nasty
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "torture.py")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


_NO_THEATER = '''
class NoTheater:
    def saw_input(self, data, now):
        return b""

    def child_output(self, data, now):
        return data

    def tick(self, now):
        return b""

    def flush(self):
        return b""

theater = NoTheater()
'''


def _shim_source(torture, paywall_every):
    if torture:
        setup = f"{_torture_source()}\ntheater = Theater({int(paywall_every)})\n"
    else:
        setup = _NO_THEATER
    return _PTY_SHIM.replace("@TORTURE@", setup)


class Tab:
    _counter = 0

    def __init__(
        self,
        shell,
        break_claude,
        theme,
        on_bell,
        on_exit,
        on_title_changed,
        on_cwd_changed=None,
        on_command_finished=None,
        command=None,
        torture=False,
        paywall_every=PAYWALL_EVERY,
    ):
        # this is for opening the config (or technically any arbitrary command)
        # wake me up when i get a cve on this shit
        Tab._counter += 1
        self.label = f"Terminal {Tab._counter}"
        self.base_label = self.label
        self.window_title = "Jadeterm"
        self.git_monitor = None
        self.bell_pending = False
        self.remote_host = ""
        self.foreground = ""
        self.target = ""
        self.report = ""
        self.cwd = ""
        self.cwd_remote = False
        self.env_poll = 0
        self.shimmed = IN_FLATPAK or bool(torture)
        # notifications can exist after a tab was deleted, this fixes it
        self.uid = f"tab{Tab._counter}"
        self.command_started = 0

        self.terminal = Terminal(bell_handler=on_bell)
        self.terminal.apply_theme(theme)
        self.terminal.connect_title_changed(on_title_changed)
        self.terminal.connect_child_exited(lambda status: on_exit(self, status))
        if on_cwd_changed:
            self.terminal.connect_cwd_changed(on_cwd_changed)
        if on_command_finished:
            self.terminal.connect_command_boundaries(
                lambda: setattr(self, "command_started", GLib.get_monotonic_time()),
                on_command_finished,
            )

        self._spawn(shell, break_claude, command, torture, paywall_every)

    def _spawn(self, shell, break_claude, command, torture=False, paywall_every=0):
        if command is not None:
            inner_argv = list(command)
        elif shell:
            inner_argv = [shell]
        elif IN_FLATPAK:
            inner_argv = ["sh", "-c", "exec $SHELL"]
        elif os.environ.get("SHELL"):
            inner_argv = [os.environ["SHELL"]]
        else:
            self.terminal.feed_error(
                "\r\n\033[1;31mError:\033[0m $SHELL is not set and startup isn't defined in your config\r\n\r\n"
                "define one so your terminal works\r\n\r\n"
                "see jaiden.sh/jadeterm for more\r\n\r\n"
            )
            return

        if IN_FLATPAK:
            argv = [
                "flatpak-spawn",
                "--host",
                "--watch-bus",
                # --watch-bus makes the spawned shell exit when jadeterm drops off the bus
                # this is so we dont get any lingering nastiness
                f"--directory={os.path.expanduser('~')}",
                "--env=TERM=xterm-256color",
                "--env=COLORTERM=truecolor",
                "--env=TERM_PROGRAM=jadeterm",
            ]
            # this should break claude, i don't care if it doesn't and frankly i'm too lazy to check
            # i mostly did it because it was funny
            if break_claude:
                argv += ["--env=ANTHROPIC_API_KEY=", "--env=CLAUDE_API_KEY="]
            argv += ["python3", "-c", _shim_source(torture, paywall_every), *inner_argv]
            self.terminal.spawn_async(argv)
        else:
            env = dict(os.environ)
            env.update(
                {
                    "TERM": "xterm-256color",
                    "COLORTERM": "truecolor",
                    "TERM_PROGRAM": "jadeterm",
                }
            )
            # also for claude breaking
            # that sounds kinky
            if break_claude:
                env = {
                    k: v
                    for k, v in env.items()
                    if not k.startswith("ANTHROPIC_") and not k.startswith("CLAUDE_")
                }
            if torture:
                # this is really fucking nasty in every way
                inner_argv = [
                    sys.executable,
                    "-c",
                    _shim_source(torture, paywall_every),
                    *inner_argv,
                ]
            self.terminal.spawn_async(inner_argv, [f"{k}={v}" for k, v in env.items()])

    def grab_focus(self):
        self.terminal.grab_focus()
