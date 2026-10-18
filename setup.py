#!/usr/bin/env python3
"""One-step setup for the Game Creations Engine (run once per machine; safe to re-run).

  python setup.py            check tools, install the /ai-game-studio Claude Code skill
  python setup.py --demo     ...then open The Office in demo mode to see the team view without running agents

Checks every tool the studio uses and prints the exact install command for anything missing. Never installs
anything by itself except the skill file (~/.claude/skills/ai-game-studio/SKILL.md).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
# (command, version args, required?, what it's for, how to install)
TOOLS = [
    ("git", ["--version"], True, "version control for every game", "winget install Git.Git"),
    ("godot_console", ["--version"], True, "the game engine (headless checks)", "winget install GodotEngine.GodotEngine"),
    ("claude", ["--version"], True, "Claude Code: the quarterback (plans, reviews)",
     "npm install -g @anthropic-ai/claude-code   (then run `claude` once to log in)"),
    ("opencode", ["--version"], True, "OpenCode: runs the coding models",
     "npm install -g opencode-ai   (then `opencode auth login` for any paid provider)"),
    ("codex", ["--version"], False, "Codex CLI: QA + image-generated art",
     "npm install -g @openai/codex   (then run `codex` once to log in)"),
    ("node", ["--version"], False, "needed to install the CLIs above", "winget install OpenJS.NodeJS.LTS"),
]


def version(cmd: str, args: list[str]) -> str | None:
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        out = subprocess.run([exe] + args, capture_output=True, text=True, timeout=30)
        return ((out.stdout or out.stderr).strip().splitlines() or ["installed"])[0][:60]
    except Exception:  # noqa: BLE001
        return "installed (version check failed)"


def main() -> int:
    print(f"Game Creations Engine setup ({(ENGINE / 'VERSION').read_text().strip()}) at {ENGINE}\n")
    ok = sys.version_info >= (3, 11)
    print(f"  {'OK' if ok else 'MISSING':<9}{'python':<15}{sys.version.split()[0]}"
          + ("" if ok else "   -> winget install Python.Python.3.12"))
    missing_required = 0 if ok else 1
    for cmd, args, required, why, how in TOOLS:
        v = version(cmd, args)
        if v:
            print(f"  {'OK':<9}{cmd:<15}{v}")
        else:
            missing_required += required
            print(f"  {'MISSING' if required else 'optional':<9}{cmd:<15}{why}\n{'':<26}-> {how}")
    if sys.platform != "win32":
        print("\n  Note: the batch files assume Windows 11; see docs/other_engines.md to adapt.")

    print(flush=True)
    subprocess.run([sys.executable, str(ENGINE / "skill" / "install_skill.py")], check=False)

    print("\nNext steps:")
    if missing_required:
        print(f"  1. Install the {missing_required} missing tool(s) above, then run `python setup.py` again.")
    print("  - Open Claude Code in an empty folder and type /ai-game-studio (or describe the game you want).")
    print("  - Preview the live team view any time: python template/office/server.py --demo")
    print("  - Full guide: README.md")
    if "--demo" in sys.argv:
        subprocess.Popen([sys.executable, str(ENGINE / "template" / "office" / "server.py"), "--demo"])
    return 1 if missing_required else 0


if __name__ == "__main__":
    sys.exit(main())
