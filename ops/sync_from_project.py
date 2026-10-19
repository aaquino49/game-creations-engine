#!/usr/bin/env python3
"""Pull the current engine machinery from a live game project back into the engine template.

Every game improves the orchestrator, supervisor and role guides as problems come up. Run this after (or during) a
game to bring those improvements home. It copies only reusable machinery (never game code or content), turns the
project's names back into placeholders, and makes the agent tables config-driven.

  python ops/sync_from_project.py "C:/path/to/Grim Turn Based"            # dry run: shows what would change
  python ops/sync_from_project.py "C:/path/to/Grim Turn Based" --apply

Afterwards: review `git diff` in the engine, run `python ops/test_orchestrator.py`, then commit.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TEMPLATE = ENGINE / "template"

# Files that are pure machinery: safe to copy from any project.
MACHINERY = [
    "orchestrator/orchestrator.py", "orchestrator/supervisor.py",
    "start.bat", "stop.bat", "supervise.bat", "play.bat", ".gitignore", ".gitattributes",
    "project/roles/coder.md", "project/roles/qa_assets.md",
    "project/roles/quarterback.md", "project/roles/supervisor.md",
    "game/tests/run_tests.gd", "game/tests/test_case.gd", "game/tests/README.md",
    "game/scripts/autoload/dev_tools.gd", "game/scripts/sim/core/dice.gd", "game/scripts/sim/core/game_data.gd",
]

# Engine-owned files (not synced): project/PROTOCOL.md, project/ARCHITECTURE.md, README/CLAUDE/AGENTS templates and
# the game scaffold. Games often let these drift or fill them with game specifics; improve them here directly.

# Words that should never survive into the generic template (checked after the transforms).
SUSPECT_RE = re.compile(r"Grim|Haven|Legion|Saint Ferro|Blighted|Raider|tactics game|R-[0-9]\b|T-[0-9]{3}")


def project_identity(project: Path) -> dict:
    cfg = json.loads((project / "orchestrator" / "config.json").read_text(encoding="utf-8"))
    godot = (project / "game" / "project.godot").read_text(encoding="utf-8")
    name = re.search(r'config/name="([^"]+)"', godot).group(1)
    exe = ""
    presets = project / "game" / "export_presets.cfg"
    if presets.exists():
        m = re.search(r'export_path="[^"]*?([^/"\\]+)\.exe"', presets.read_text(encoding="utf-8"))
        exe = m.group(1) if m else ""
    lanes = cfg.get("lanes") or []
    slug = ""
    if lanes:
        m = re.search(r"([A-Za-z0-9]+)_lane[A-Z]$", Path(lanes[0]["dir"]).name)
        slug = m.group(1) if m else ""
    local_cfg = project / "orchestrator" / "config.local.json"
    local = json.loads(local_cfg.read_text(encoding="utf-8")) if local_cfg.exists() else {}
    topic = (local.get("notify") or {}).get("ntfy_topic") or (cfg.get("notify") or {}).get("ntfy_topic", "")
    return {"name": name, "exe": exe, "slug": slug, "topic": topic}


def replace_block(s: str, start: str, new: str) -> str:
    """Replace a Python dict literal assignment `NAME = {...}` (brace-matched) with `new`."""
    i = s.find(start)
    if i < 0:
        return s
    j = s.index("{", i)
    depth = 0
    for k in range(j, len(s)):
        depth += {"{": 1, "}": -1}.get(s[k], 0)
        if depth == 0:
            return s[:i] + new + s[k + 1:]
    return s


def genericize(rel: str, text: str, ident: dict) -> str:
    pairs = [(ident["name"], "{{GAME_NAME}}")]
    if ident["exe"]:
        pairs.append((ident["exe"] + ".exe", "{{EXE_NAME}}.exe"))
    if ident["slug"]:
        pairs += [(f"{ident['slug']}_lane", "{{SLUG}}_lane")]
    if ident["topic"]:
        pairs.append((ident["topic"], "{{NTFY_TOPIC}}"))
    for a, b in pairs:
        text = text.replace(a, b)

    if rel == "orchestrator/orchestrator.py":
        text = replace_block(text, "AGENT_NAMES = {", '''# Agent labels, models and accounts come from config.json ("label", "model", "account" per agent).
# Positions are roles (quarterback, qa_lead, coder_1...); the model under each is swappable.
# ROLES maps the two appointed positions to agent ids (legacy default: claude/codex).
# Agents sharing an account (e.g. QA lead and coder_2 on one OpenAI plan) share its usage limit.
AGENT_NAMES = {name: a.get("label", name) for name, a in CONFIG["agents"].items()}''')
        text = re.sub(r'CODER_OWNERS = \{[^}]*\}',
                      'CODER_OWNERS = {"coder", *CONFIG.get("coders", []), *CONFIG.get("coders_alt", [])}', text, count=1)
        text = replace_block(text, "ACCOUNT = {",
                             'ACCOUNT = {name: a.get("account", name) for name, a in CONFIG["agents"].items()}')
        text = replace_block(text, "PROBE_AGENT = {", '''PROBE_AGENT: dict[str, str] = {}
for _name, _acct in ACCOUNT.items():  # the first agent listed for an account is the one probed
    PROBE_AGENT.setdefault(_acct, _name)''')
        text = re.sub(r'return list\(CONFIG\.get\("coders"\) or \[[^\]]*\]\)', 'return list(CONFIG.get("coders") or [])', text)
        text = re.sub(r'paid = set\(CONFIG\.get\("paid_agents", \[[^\]]*\]\)\)', 'paid = set(CONFIG.get("paid_agents", []))', text)
        text = text.replace('An explicit owner ("deepseek"/"muse") starts with it.', "An explicit owner naming one of the coders starts with it.")

    if rel == "project/PROTOCOL.md":
        m = re.search(r"\| Agent \| (Tool|Command) \| Role \|.*?\n\n", text, re.S)
        if m:
            text = text.replace(m.group(0), "{{TEAM_TABLE}}\n\n", 1)

    if rel == "project/roles/supervisor.md":
        text = re.sub(r"Falling back to `[a-z_]+` when the preferred models are rate-limited is expected, not a bug\.",
                      "Falling back along the `fallback` chains (including to a paid agent listed in `paid_agents`) when the "
                      "preferred models are rate-limited is expected, not a bug.", text)
    if rel == "game/tests/README.md":
        text = re.sub(r'load\("res://scenes/[a-z_]+/[a-z_]+\.tscn"\)', 'load("res://scenes/<area>/<screen>.tscn")', text)

    if rel.startswith("project/roles/"):
        for pat, rep in [
            (r"a finished, fun, polished [a-z -]*?game,", "a finished, fun, polished game,"),
            (r"# Role: Coder \([^)]*\)", "# Role: Coder (the coding models listed in orchestrator/config.json)"),
            (r"a Godot 4\.\d GDScript [a-z -]*?game", "a Godot 4 GDScript game"),
            (r"From v\d\.\d \(owner request R-\d+\) you may", "You may"),
            (r"\*\*Coders are free, fast, mid-tier models\*\* \([^)]*\)\.",
             "**Coders** are the models in `orchestrator/config.json` `coders`, one per lane, alternating on retries when there are several."),
            (r"\*\*Codex \(GPT-[^)]*\)\*\*", "**Codex**"),
            (r"list \(camping skills[^)]*\)", "list (new systems, classes, regions, modes)"),
            (r"more content \(rooms, curios[^)]*\)", "more content (levels, items, enemies)"),
        ]:
            text = re.sub(pat, rep, text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    project = Path(a.project).resolve()
    ident = project_identity(project)
    print(f"Project: {ident}")
    changed = 0
    suspects = []
    for rel in MACHINERY:
        src = project / rel
        if not src.exists():
            print(f"  skip (missing in project): {rel}")
            continue
        new = genericize(rel, src.read_text(encoding="utf-8"), ident)
        dst = TEMPLATE / rel
        old = dst.read_text(encoding="utf-8") if dst.exists() else ""
        for n, line in enumerate(new.splitlines(), 1):
            if SUSPECT_RE.search(line):
                suspects.append(f"{rel}:{n}: {line.strip()[:110]}")
        if new.replace("\r\n", "\n") == old.replace("\r\n", "\n"):
            continue
        changed += 1
        diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0))
        adds = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
        rems = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
        print(f"  {'UPDATE' if a.apply else 'would update'} {rel}  (+{adds} / -{rems})")
        if a.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(new, encoding="utf-8", newline="\r\n" if rel.endswith(".bat") else "\n")
    if rel_check := [s for s in suspects]:
        print(f"\n{len(rel_check)} line(s) still look game-specific. Review and genericize them by hand:")
        for s in rel_check[:40]:
            print("   " + s)
    print(f"\n{changed} file(s) {'updated' if a.apply else 'would change'}.")
    if a.apply:
        import ast
        ast.parse((TEMPLATE / "orchestrator/orchestrator.py").read_text(encoding="utf-8").replace("{{GAME_NAME}}", "X"))
        ast.parse((TEMPLATE / "orchestrator/supervisor.py").read_text(encoding="utf-8").replace("{{GAME_NAME}}", "X"))
        print("Template orchestrator and supervisor parse OK. Next: python ops/test_orchestrator.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
