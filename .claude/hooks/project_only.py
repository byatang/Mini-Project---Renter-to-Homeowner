"""Hook 1: block reading or writing any file outside the project folder.

Runs before file tools (Read, Write, Edit, Glob, Grep...) and terminal commands.
Exit code 2 blocks the action and tells Claude why.
"""

import json
import os
import re
import sys

PROJECT = os.path.normcase(os.path.realpath(
    os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(os.path.dirname(__file__), "..", "..")))
HOME = os.path.expanduser("~")
ENV_DIRS = {  # shell shortcuts that point outside the project
    r"\$env:USERPROFILE": HOME, r"%USERPROFILE%": HOME, r"\$HOME\b": HOME,
    r"\$env:TEMP": os.environ.get("TEMP", HOME), r"%TEMP%": os.environ.get("TEMP", HOME),
    r"\$env:APPDATA": os.environ.get("APPDATA", HOME), r"%APPDATA%": os.environ.get("APPDATA", HOME),
}


def resolve(path, cwd):
    m = re.match(r"^/([a-zA-Z])/(.*)$", path)          # Git Bash style: /c/Users/...
    if m:
        path = f"{m.group(1)}:/{m.group(2)}"
    for pattern, target in ENV_DIRS.items():
        path = re.sub(pattern, lambda _: target.replace("\\", "/"), path, flags=re.I)
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.normcase(os.path.realpath(path))


def is_inside(path, cwd):
    p = resolve(path, cwd)
    return p == PROJECT or p.startswith(PROJECT + os.sep)


def paths_in_command(command):
    """Best-effort: pull out anything in a terminal command that looks like a path."""
    tokens = re.findall(r'"([^"]*)"|\'([^\']*)\'|(\S+)', command)
    for token in (next(t for t in group if t) for group in tokens if any(group)):
        token = token.strip(";|&()<>,")
        drive = re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/].*", token)
        if drive:
            yield drive.group(0)
        elif re.match(r"^(~|/[a-zA-Z]/|/tmp/|\$HOME|\$env:|%\w+%)", token, flags=re.I):
            yield token
        elif ".." in re.split(r"[\\/]", token):
            yield token


def main():
    data = json.load(sys.stdin)
    tool, args = data.get("tool_name", ""), data.get("tool_input", {})
    cwd = data.get("cwd") or PROJECT

    if tool in ("Bash", "PowerShell"):
        candidates = list(paths_in_command(args.get("command", "")))
    else:
        candidates = [args[k] for k in ("file_path", "notebook_path", "path") if args.get(k)]

    outside = [p for p in candidates if not is_inside(p, cwd)]
    if outside:
        print(f"Blocked by project hook: '{outside[0]}' is outside the project folder. "
              f"This project only allows files inside {PROJECT}.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
