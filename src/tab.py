import os

from .paths import IN_FLATPAK
from .terminal import Terminal


class Tab:
    _counter = 0

    def __init__(
        self,
        shell,
        break_claude,
        theme,
        bell,
        on_exit,
        on_title_changed,
        on_cwd_changed=None,
        command=None,
    ):
        # this is for opening the config (or technically any arbitrary command)
        # wake me up when i get a cve on this shit
        Tab._counter += 1
        self.label = f"Terminal {Tab._counter}"

        self.terminal = Terminal(bell_handler=bell.ring if bell else None)
        self.terminal.apply_theme(theme)
        self.terminal.connect_title_changed(on_title_changed)
        self.terminal.connect_child_exited(lambda status: on_exit(self, status))
        if on_cwd_changed:
            self.terminal.connect_cwd_changed(on_cwd_changed)

        self._spawn(shell, break_claude, command)

    def _spawn(self, shell, break_claude, command):
        # this is for priority: config open/command mode -> `startup` in config -> $SHELL, there's a flatpak helper too
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
            # flatpak-spawn is stupid, this should allocate a pty on this host
            argv += [
                "python3",
                "-c",
                "import pty,sys; raise SystemExit(pty.spawn(sys.argv[1:]))",
                *inner_argv,
            ]
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
            self.terminal.spawn_async(inner_argv, [f"{k}={v}" for k, v in env.items()])

    def grab_focus(self):
        self.terminal.grab_focus()
