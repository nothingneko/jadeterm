import os


_FORGES = (
    ("github.com", "github"),
    ("codeberg.org", "codeberg"),
    # one of these days i'll add a pagure logo but right now i'm fuckin lazy and they're all icos
    ("pagure.io", "fedora"),
    ("src.fedoraproject.org", "fedora"),
    ("fedoraproject.org", "fedora"),
    ("git.sr.ht", "sourcehut"),
    ("sr.ht", "sourcehut"),
)

GENERIC_FORGE = "git"

FORGE_NAMES = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "codeberg": "Codeberg",
    "sourcehut": "SourceHut",
    "fedora": "Fedora",
}


class RepoInfo:
    def __init__(self, root, name, forge):
        self.root = root
        self.name = name
        self.forge = forge


def _remote_host(remote):
    text = remote.strip()
    if not text or text.startswith(("/", ".", "~")):
        return ""
    if "://" in text:
        text = text.split("://", 1)[1]
    if "@" in text:
        text = text.split("@", 1)[1]
    return text.split("/")[0].split(":")[0].lower()


def _forge(remote):
    host = _remote_host(remote)
    if not host:
        return GENERIC_FORGE
    for domain, slug in _FORGES:
        if host == domain or host.endswith("." + domain):
            return slug
    # self hosted gitlab is just gitlab so whatever
    if host == "gitlab" or host.startswith("gitlab.") or ".gitlab." in host:
        return "gitlab"
    return GENERIC_FORGE


def _gitdir(path):
    # in submodules .git is a file
    # it took me too long to figure this out because i'm an idiot
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(4096)
    except OSError:
        return ""
    for line in head.splitlines():
        if line.startswith("gitdir:"):
            return line.split(":", 1)[1].strip()
    return ""


def _find_repo(path):
    current = path
    while True:
        candidate = os.path.join(current, ".git")
        if os.path.isdir(candidate):
            return current, candidate
        if os.path.isfile(candidate):
            gitdir = _gitdir(candidate)
            if gitdir:
                return current, os.path.normpath(os.path.join(current, gitdir))
            return current, ""
        parent = os.path.dirname(current)
        if parent == current:
            return "", ""
        current = parent


def _config_path(gitdir):
    # i don't use linked worktrees but i feel bad breaking things
    commondir = os.path.join(gitdir, "commondir")
    try:
        with open(commondir, encoding="utf-8", errors="replace") as handle:
            shared = handle.read().strip()
    except OSError:
        shared = ""
    if shared:
        gitdir = os.path.normpath(os.path.join(gitdir, shared))
    return os.path.join(gitdir, "config")


def _origin_url(config_path):
    in_origin = False
    try:
        with open(config_path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("["):
                    in_origin = stripped.replace(" ", "").startswith('[remote"origin"]')
                elif in_origin and "=" in stripped:
                    key, value = stripped.split("=", 1)
                    if key.strip() == "url":
                        return value.strip()
    except OSError:
        return ""
    return ""


def _repo_name(remote, root):
    text = remote.strip().rstrip("/")
    if not text or text.startswith(("/", ".", "~")):
        return os.path.basename(root)
    if text.endswith(".git"):
        text = text[:-4]
    # awful code, really truly terrible
    # to detect the owner/repo
    parts = [p for p in text.replace(":", "/").split("/") if p]
    if len(parts) >= 3:
        return "/".join(parts[-2:])
    return parts[-1] if parts else os.path.basename(root)


def lookup(path):
    root, gitdir = _find_repo(path)
    if not root:
        return None
    remote = _origin_url(_config_path(gitdir)) if gitdir else ""
    return RepoInfo(root=root, name=_repo_name(remote, root), forge=_forge(remote))
