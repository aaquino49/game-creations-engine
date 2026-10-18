#!/usr/bin/env python3
"""Install the /ai-game-studio Claude Code skill, pointing at this engine folder (the master copy).

  python skill/install_skill.py

Writes ~/.claude/skills/ai-game-studio/SKILL.md from skill/SKILL.md with the engine path filled in, and removes the
old bundled copies (assets/, scripts/, references/) there, since everything is now read from the engine folder.
Re-run it after editing skill/SKILL.md or moving the engine folder.
"""
import shutil
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
DEST = Path.home() / ".claude" / "skills" / "ai-game-studio"


def main() -> int:
    text = (ENGINE / "skill" / "SKILL.md").read_text(encoding="utf-8").replace("{{ENGINE_PATH}}", ENGINE.as_posix())
    DEST.mkdir(parents=True, exist_ok=True)
    for old in ("assets", "scripts", "references"):
        if (DEST / old).exists():
            shutil.rmtree(DEST / old)
            print(f"removed old bundled {DEST / old}")
    (DEST / "SKILL.md").write_text(text, encoding="utf-8")
    print(f"installed {DEST / 'SKILL.md'} -> engine at {ENGINE}")
    print("In Claude Code: type /ai-game-studio, or ask to build a new game with the game creations engine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
