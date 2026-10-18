#!/usr/bin/env python3
"""Create a new game project from the Game Creations Engine template.

Example (the Grim Haven lineup):
  python scaffold.py --target "C:/Users/me/Projects/My Game" --name "My Game" --pitch "A grim roguelite." \\
    --agent claude=claude:claude-opus-5-5 \\
    --agent codex=codex:gpt-6.1-sol \\
    --agent codex_luna=codex:gpt-6-luna \\
    --agent beam=opencode:opencode/beam-free \\
    --agent deepseek=opencode:opencode/deepseek-v4.1-flash-free \\
    --agent muse_paid=opencode:meta/muse-spark-1.3-contributor --paid muse_paid \\
    --coders codex_luna \\
    --fallback "codex_luna:*=beam,deepseek,muse_paid" --fallback "codex:qa=beam,deepseek,muse_paid" \\
    --fallback "claude:*=codex,muse_paid" --lanes 3

Agent kinds:  claude:<model>   codex:<model>   opencode:<provider/model>   cmd:<json list with {prompt}>
Required agent names: `claude` (quarterback: plans, reviews, design tasks) and `codex` (QA and assets).
The agents' accounts: claude -> anthropic, codex -> openai (agents on one account share its usage limit),
opencode models each get their own account (their free tiers are limited per model).
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TEMPLATE = ENGINE / "template"
DEFAULT_PRESET = ENGINE / "presets" / "default.json"
TEXT_EXT = {".py", ".md", ".gd", ".tscn", ".godot", ".cfg", ".json", ".bat", ".txt", ".gitignore", ".gitattributes"}


def agent_spec(name: str, spec: str) -> dict:
    kind, _, arg = spec.partition(":")
    if kind == "claude":
        return {"cmd": ["claude", "-p", "{prompt}", "--model", arg, "--dangerously-skip-permissions"],
                "account": "anthropic", "label": f"Claude {arg}"}
    if kind == "codex":
        return {"cmd": ["codex", "exec", "-m", arg, "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check",
                        "{prompt}", "{images}"], "account": "openai", "label": f"Codex {arg}"}
    if kind == "opencode":
        # --print-logs/--log-level ERROR make OpenCode print rate-limit errors, which it otherwise retries silently
        # forever; watch_rate_limit lets the orchestrator kill the run on the first one and fall back.
        return {"cmd": ["opencode", "run", "--auto", "--print-logs", "--log-level", "ERROR", "-m", arg, "{prompt}"],
                "account": name, "label": f"{arg} via OpenCode", "watch_rate_limit": True}
    if kind == "cmd":
        cmd = json.loads(arg)
        assert "{prompt}" in cmd, "cmd agents need a {prompt} placeholder"
        return {"cmd": cmd, "account": name, "label": name}
    raise SystemExit(f"unknown agent kind in {name}={spec}")


def load_preset(a: argparse.Namespace) -> dict:
    """Preset JSON (agents as name -> "kind:arg", coders, paid, lanes, fallback). CLI flags add to / override it."""
    path = Path(a.preset) if a.preset else (DEFAULT_PRESET if not a.agent and not a.no_preset else None)
    if not path:
        return {}
    preset = json.loads(path.read_text(encoding="utf-8"))
    print(f"Using preset {path}")
    return preset


def build_config(a: argparse.Namespace, slug: str, topic: str) -> dict:
    preset = load_preset(a)
    agents = {name: agent_spec(name, spec) for name, spec in (preset.get("agents") or {}).items()}
    for item in a.agent or []:
        name, _, spec = item.partition("=")
        agents[name.strip()] = agent_spec(name.strip(), spec.strip())
    agents.setdefault("claude", agent_spec("claude", "claude:claude-opus-5-5"))
    agents.setdefault("codex", agent_spec("codex", "codex:gpt-6.1-sol"))
    a.paid = list(dict.fromkeys((preset.get("paid") or []) + (a.paid or [])))
    for p in a.paid:
        agents[p]["label"] += " (paid)"
    fallback = {k: list(v) for k, v in (preset.get("fallback") or {}).items()}
    for item in a.fallback or []:
        key, _, chain = item.partition("=")
        fallback[key.strip()] = [c.strip() for c in chain.split(",") if c.strip()]
    coders = [c.strip() for c in a.coders.split(",") if c.strip()] if a.coders else list(preset.get("coders") or ["codex"])
    if a.lanes is None:
        a.lanes = int(preset.get("lanes", 3))
    for name in coders + [x for ch in fallback.values() for x in ch]:
        if name not in agents:
            raise SystemExit(f"agent '{name}' is used but not defined (add --agent {name}=...)")
    lane_root = Path(a.lane_root).expanduser()
    lanes = [{"name": chr(ord("B") + i), "dir": (lane_root / f"{slug}_lane{chr(ord('B') + i)}").as_posix()}
             for i in range(max(0, a.lanes - 1))]
    return {
        "max_attempts": 3, "plan_every_n_done": 6, "agent_timeout_minutes": 60, "stuck_retry_minutes": 60,
        "godot": a.godot, "coders": coders, "agents": agents, "fallback": fallback, "paid_agents": a.paid or [],
        "lanes": lanes, "lane_b": {"merge_wait_minutes": 120}, "background_planning": True,
        "stop_on_usage_limit": False, "expansion_after_v1": not a.no_expansion, "default_limit_minutes": 60,
        "probe_every_minutes": 15, "godot_watchdog_minutes": 10,
        "abort_output_re": 'level=ERROR .*message="stream error".*(Rate limit|Too Many Requests|insufficient balance|quota)',
        "abort_after_matches": 1,
        "handoff_at_percent": {"primary": 97, "secondary": 98},
        "supervisor": {"stall_minutes": 40, "lane_idle_minutes": 20, "cooldown_minutes": 45,
                       "agents": ["claude", "codex", *(a.paid or [])], "timeout_minutes": 30},  # paid last: both subscriptions can be limited at once
        "notify": {"ntfy_topic": topic, "email": "", "min_minutes_between": 60},
        "_notes": "Generated by the Game Creations Engine (scripts/scaffold.py). Change coders/fallback here, commit, then create project/RESTART.",
    }


def team_table(cfg: dict) -> str:
    rows = ["| Agent | Command | Role |", "|---|---|---|",
            f"| **claude** | {cfg['agents']['claude']['label']} | Quarterback: product manager, project manager, tech "
            f"lead, final reviewer. Owns the GDD, the backlog and all decisions. |",
            f"| **codex** | {cfg['agents']['codex']['label']} | QA (tests, playtests, bug reports) and asset producer. |"]
    for i, c in enumerate(cfg["coders"]):
        rows.append(f"| **{c}** | {cfg['agents'][c]['label']} | Coder{' (all lanes)' if len(cfg['coders']) == 1 else ''}. |")
    others = sorted({x for ch in cfg["fallback"].values() for x in ch} - set(cfg["coders"]) - {"claude", "codex"})
    for o in others:
        role = "Paid cover, only when every free/subscription option is rate-limited." if o in cfg["paid_agents"] \
            else "Fallback when the preferred agent is rate-limited."
        rows.append(f"| **{o}** | {cfg['agents'][o]['label']} | {role} |")
    rows.append("| **Orchestrator** | `orchestrator/orchestrator.py` | A plain script with no AI. Runs the loop, calls the "
                "agents, runs builds and tests, commits. **It is the only writer of `project/board.json`.** |")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--pitch", required=True, help="one sentence")
    ap.add_argument("--exe", help="build name without .exe (default: name without spaces)")
    ap.add_argument("--slug", help="short id for worktree folders (default: initials)")
    ap.add_argument("--agent", action="append", help="name=kind:arg (see module doc)")
    ap.add_argument("--coders", help="comma list of agent names that code (one per lane, alternating on retries)")
    ap.add_argument("--fallback", action="append", help='"agent:step=a,b,c" (step: *, qa, plan, review, work-code, ...)')
    ap.add_argument("--paid", action="append", help="agent name that costs money (kept last in fallback chains)")
    ap.add_argument("--lanes", type=int, default=None, help="total lanes including lane A (default: preset, else 3)")
    ap.add_argument("--preset", help="preset JSON (default: presets/default.json when no --agent flags are given)")
    ap.add_argument("--no-preset", action="store_true", help="ignore presets/default.json")
    ap.add_argument("--lane-root", default="~", help="folder for worktree lanes, outside OneDrive (default: home)")
    ap.add_argument("--godot", default="godot")
    ap.add_argument("--ntfy-topic", help="push alert topic (default: random)")
    ap.add_argument("--no-expansion", action="store_true", help="stop when v1 is done instead of expanding")
    ap.add_argument("--force", action="store_true", help="allow a non-empty target")
    a = ap.parse_args()

    target = Path(a.target).expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not a.force:
        raise SystemExit(f"{target} is not empty (use --force to scaffold into it anyway)")
    exe = a.exe or re.sub(r"[^A-Za-z0-9]", "", a.name.title())
    slug = (a.slug or "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", a.name)).lower() or "game")[:8]
    topic = a.ntfy_topic or f"{re.sub(r'[^a-z0-9]+', '-', a.name.lower()).strip('-')}-{secrets.token_hex(6)}"
    cfg = build_config(a, slug, topic)
    subs = {"{{GAME_NAME}}": a.name, "{{GAME_NAME_UPPER}}": a.name.upper(), "{{EXE_NAME}}": exe, "{{SLUG}}": slug,
            "{{PITCH}}": a.pitch.replace('"', "'"), "{{NTFY_TOPIC}}": topic, "{{TEAM_TABLE}}": team_table(cfg)}

    for src in TEMPLATE.rglob("*"):
        if src.is_dir():
            continue
        dst = target / src.relative_to(TEMPLATE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in TEXT_EXT or src.name in (".gitignore", ".gitattributes"):
            text = src.read_text(encoding="utf-8")
            for k, v in subs.items():
                text = text.replace(k, v)
            dst.write_text(text, encoding="utf-8", newline="\r\n" if src.suffix == ".bat" else "\n")
        else:
            shutil.copy2(src, dst)
    for d in ("project/tasks", "project/milestones", "game/assets", "builds", "asset_library"):
        (target / d).mkdir(parents=True, exist_ok=True)
        if d != "builds":  # git skips empty folders; the orchestrator and fresh clones need these to exist
            (target / d / ".gitkeep").touch()
    (target / "orchestrator" / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    board = {"project": a.name, "next_id": 1, "tasks": [], "milestones_complete": ["M0"], "v1_complete": False,
             "project_complete": False}
    (target / "project" / "board.json").write_text(json.dumps(board, indent=2), encoding="utf-8")
    placeholder = re.compile(r"\{\{[A-Z_]+\}\}")  # not plain "{{": Python f-strings use it for literal braces
    leftovers = [str(p.relative_to(target)) for p in target.rglob("*") if p.is_file() and p.suffix in TEXT_EXT
                 and placeholder.search(p.read_text(encoding="utf-8", errors="ignore"))]
    print(json.dumps({"target": str(target), "exe": exe, "slug": slug, "ntfy_topic": topic,
                      "coders": cfg["coders"], "lanes": 1 + len(cfg["lanes"]),
                      "unfilled_placeholders": leftovers}, indent=2))
    if leftovers:
        sys.exit(2)


if __name__ == "__main__":
    main()
