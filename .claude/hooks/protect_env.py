"""Hook 2: block access to .env files (where the API keys live). .env.example is allowed.

Runs before file tools and terminal commands. Exit code 2 blocks the action.
"""

import fnmatch
import json
import os
import re
import sys

ALLOWED = {".env.example"}


def is_env_name(name):
    return re.fullmatch(r"\.env(\..+)?", name) is not None and name not in ALLOWED


def env_in_command(command):
    """Find .env, .env.local, etc. in a command, plus wildcards like .en* that would match .env."""
    for match in re.finditer(r"(?<![\w.-])\.env(?:\.[\w.-]+)?(?![\w-])", command):
        if match.group(0) not in ALLOWED:
            return match.group(0)
    for token in re.findall(r"[^\s\"';|&()<>]+", command):
        base = re.split(r"[\\/]", token)[-1]
        if any(c in base for c in "*?[") and fnmatch.fnmatchcase(".env", base):
            return token
    return None


def main():
    data = json.load(sys.stdin)
    tool, args = data.get("tool_name", ""), data.get("tool_input", {})

    if tool in ("Bash", "PowerShell"):
        hit = env_in_command(args.get("command", ""))
    else:
        values = [args.get(k) for k in ("file_path", "notebook_path", "path", "glob") if args.get(k)]
        hit = next((v for v in values if is_env_name(os.path.basename(v))), None)

    if hit:
        print(f"Blocked by project hook: '{hit}' is a secrets file (.env). "
              "Its contents are off-limits. .env.example is allowed.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
