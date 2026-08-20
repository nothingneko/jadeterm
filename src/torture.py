# dear reader
# this is the nastiest code i or claude has ever written
# i wrote most of it, you can tell by the fact that it's terrible

"""this is torture mode

if you don't get it consider trying to read an academic journal

if you haven't done that already consider yourself lucky and close this file
"""

import random
import re

REJECT_CHANCE = 0.30
# emacs is love, emacs is life
EMACS_CHANCE = 0.08
REVIEW_SECONDS = 2.5
EMBARGO_SECONDS = 8.0
PAYWALL_BEAT = 1.2
PAYWALL_EVERY = 5

HOLD_LIMIT = 8192
HOLD_CEILING = 30.0

_ALT_SCREEN_ON = b"\033[?1049h"
_ALT_SCREEN_OFF = b"\033[?1049l"

_DIM = "\033[2m"
_RED = "\033[31m"
_AMBER = "\033[33m"
_OFF = "\033[0m"

_ALTERNATIVES = {
    "cat": "bat",
    "cd": "pushd",
    "cp": "rsync",
    "curl": "wget",
    "df": "duf",
    "du": "dust",
    "echo": "printf",
    "find": "fd",
    "git": "deltadb",
    "grep": "ripgrep",
    "kill": "negotiation",
    "ls": "find",
    "make": "meson",
    "man": "info",
    "mv": "rsync",
    "nano": "micro",
    "ps": "procs",
    "python3": "fortran",
    "rm": "shred",
    "ssh": "telnet",
    "sudo": "run0",
    "top": "htop",
    "vim": "vi",
    "wget": "curl",
}

_PRIOR_WORK = ("awk", "sed", "ed", "cpio", "uucp", "TECO", "punched cards")

_REJECTIONS = (
    "The author runs {cmd} without acknowledging prior work in {arg} (1984).",
    "Major revisions required. Have you considered {alt}?",
    "The contribution of {cmd} over {alt} is unclear.",
    "Reviewer 2: the results of {cmd} did not reproduce on my machine.",
    "Novelty concerns: {cmd} has appeared in the literature since 1979.",
    "The sample size (n={n}) does not support the claims made by {cmd}.",
    "Ensure you cite before invoking {cmd} again.",
    "Out of scope. Consider submitting {cmd} to a specialist venue.",
    "The manuscript would benefit from review by a native {alt} speaker.",
)

_PAYWALL = (
    "── Preview only ──────────────────────────────",
    "Purchase PDF — ${price} (24-hour access)",
    "Institutional login  ·  Already purchased?",
)

# this is so we can randomly generate the price, this is a reference to how elsevier generates their prices
PRICE_LOW = 20.01
PRICE_HIGH = 58.99
NICE_PRICE = 420.69
NICE_PRICE_CHANCE = 0.05


_ESCAPES = re.compile(rb"\033(\[[0-9;?]*[ -/]*[@-~]|\][^\007\033]*(\007|\033\\\\)?|.)")


def _blank(line):
    return not _ESCAPES.sub(b"", line).strip()


def _line(text):
    return (text + "\r\n").encode()


def alternative(command):
    if random.random() < EMACS_CHANCE:
        return "emacs"
    return _ALTERNATIVES.get(command, "emacs")


def rejection(line):
    words = line.split()
    command = words[0] if words else "sh"
    args = words[1:]
    return random.choice(_REJECTIONS).format(
        cmd=command,
        arg=args[0] if args else random.choice(_PRIOR_WORK),
        alt=alternative(command),
        n=len(args),
    )


def price():
    if random.random() < NICE_PRICE_CHANCE:
        return NICE_PRICE
    return round(random.uniform(PRICE_LOW, PRICE_HIGH), 2)


def paywall_block():
    charge = f"{price():.2f}"
    return b"".join(
        _line(_AMBER + text.format(price=charge) + _OFF) for text in _PAYWALL
    )


def embargo_bar(fraction):
    months = min(12, int(fraction * 12))
    filled = "█" * months + "░" * (12 - months)
    return (
        f"\r\033[2K{_AMBER}Embargoed — available in 12 months{_OFF}  "
        f"[{filled}]  {months}/12"
    ).encode()


class Theater:
    """this is for torture and not much else

    it won't fuck your shit up don't worry
    """
# all of this is to prevent it from looking goofy, despite this it still looks goofy
# bugs in torture mode if it's genuienly enabled will not be fixed unless they piss me off on the grounds that i don't care and you aren't paying me
    def __init__(self, paywall_every=PAYWALL_EVERY):
        self.paywall_every = max(1, int(paywall_every))
        self.typed = b""
        self.count = 0
        self.purchased = set()
        self.in_program = False
        self.mode = None
        self.command = ""
        self.hold_until = 0.0
        self.buffer = b""
        self.verdict = b""
        self.headline_sent = False
        self.echo_done = False
        self.announce = b""
        self.embargo_start = 0.0
        self.embargo_at = random.randint(2, 9)
        self.embargoed = False

    def saw_input(self, data, now):
        if self.mode:
            return self._flush()
        submitted = False
        for byte in data:
            if byte in (13, 10):
                submitted = True
            elif byte in (8, 127):
                self.typed = self.typed[:-1]
            elif byte == 3:
                self.typed = b""
            elif 32 <= byte < 127:
                self.typed += bytes((byte,))
        return self._begin(now) if submitted else b""

    def child_output(self, data, now):
        if _ALT_SCREEN_ON in data:
            self.in_program = True
        if _ALT_SCREEN_OFF in data:
            self.in_program = False
        if not self.mode:
            return data
        if self.in_program:
            return self._flush() + data
        self.buffer += data
        shown = b""
        if not self.echo_done:
            echo, newline, rest = self.buffer.partition(b"\n")
            if not newline:
                return b""
            self.buffer = rest
            self.echo_done = True
            shown += echo + newline + self.announce
            self.announce = b""
        if self.mode == "paywall" and not self.headline_sent:
            return shown + self._sell(now)
        if len(self.buffer) > HOLD_LIMIT:
            return shown + self._flush()
        return shown

    def tick(self, now):
        if not self.mode:
            return b""
        if self.mode == "embargo":
            if not self.echo_done:
                return b"" if now < self.hold_until else self._flush()
            if now < self.hold_until:
                return embargo_bar((now - self.embargo_start) / EMBARGO_SECONDS)
            return embargo_bar(1.0) + b"\r\033[2K" + self._flush()
        if now >= self.hold_until:
            return self._flush()
        return b""

    def _begin(self, now):
        command = self.typed.decode("utf-8", "replace").strip()
        self.typed = b""
        if not command or self.in_program:
            return b""
        self.count += 1
        self.command = command
        self.buffer = b""
        self.verdict = b""
        self.headline_sent = False
        self.echo_done = False
        self.announce = b""

        if not self.embargoed and self.count >= self.embargo_at:
            self.embargoed = True
            self.mode = "embargo"
            self.embargo_start = now
            self.hold_until = now + EMBARGO_SECONDS
            return b""
        if self.count % self.paywall_every == 0 and command not in self.purchased:
            self.mode = "paywall"
            self.hold_until = now + HOLD_CEILING
            return b""
        self.mode = "review"
        self.hold_until = now + REVIEW_SECONDS
        if random.random() < REJECT_CHANCE:
            self.verdict = _line(_RED + rejection(command) + _OFF)
        self.announce = _line(_DIM + "Under review… (Reviewer 2 assigned)" + _OFF)
        return b""

    def _sell(self, now):
        shown = b""
        while not self.headline_sent:
            headline, newline, rest = self.buffer.partition(b"\n")
            if not newline:
                break
            self.buffer = rest
            shown += headline + newline
            if _blank(headline):
                continue
            self.headline_sent = True
            self.hold_until = now + PAYWALL_BEAT
            self.purchased.add(self.command)
            shown += paywall_block()
        return shown

    def flush(self):
        return self._flush()

    def _flush(self):
        out = self.announce + self.verdict + self.buffer
        self.announce = b""
        self.mode = None
        self.buffer = b""
        self.verdict = b""
        return out


class NoTheater:
    def saw_input(self, data, now):
        return b""

    def child_output(self, data, now):
        return data

    def tick(self, now):
        return b""

    def flush(self):
        return b""
