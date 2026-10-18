#!/usr/bin/env python3
"""The Office: a cute, optional window onto the AI team.

  office.bat                          (or: python office/server.py)
  python office/server.py --lan       also reachable from your phone on the same Wi-Fi
  python office/server.py --project "C:/path/to/game" --port 8766

Serves a small web page that shows every agent as a little person: at a desk when working (with what they're on),
at the coffee machine or on the couch when idle, asleep when rate-limited, plus a progress bar per milestone.
With no flag it only READS project files (STATUS.md, events.log, board.json, config.json, runs/); opening or
closing it has no effect on the team. With --manage it also accepts writes (controls, owner requests, health
tools); every write needs the X-Office-Token printed at startup, and only localhost (or the LAN IP with --lan)
may call. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hmac
import json
import mimetypes
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # overridden by --project
_procs = {"orchestrator": None, "supervisor": None, "checked": 0.0}
_cache: dict = {"t": 0.0, "state": None}
_lock = threading.Lock()
DEMO = False
MANAGE = False  # --manage enables every write feature; without it the server never writes
TOKEN = ""  # manage-mode token, generated at startup (or --token)
LAN_IP = ""  # set at startup when --lan is passed
MAX_BODY = 64 * 1024
_write_lock = threading.Lock()  # serialises read-modify-write of project files
_probe = {"running": False, "results": {}}
_probe_lock = threading.Lock()
_shots: dict = {"t": 0.0, "data": []}
_stats_cache: dict = {}  # hours -> {"t": float, "data": dict}
_opencode: dict = {"t": 0.0, "days1": None, "days7": None, "error": "not loaded yet"}
_opencode_lock = threading.Lock()
_models: dict = {"t": 0.0, "data": []}  # `opencode models` list, cached for 1 h
_models_lock = threading.Lock()
TASK_ID_RE = re.compile(r"^T-\d+$")
MODEL_ID_RE = re.compile(r"^[\w.][\w./:@-]{0,99}$")  # no leading "-": it would read as a CLI flag
AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
ACCOUNT_ID_RE = re.compile(r"^[\w-]{1,40}$")
FALLBACK_STEPS = {"*", "work", "qa", "plan", "review", "work-qa", "work-asset"}
ALLOWED_SUFFIXES = {".png", ".json", ".log", ".md", ".patch", ".txt"}
NOTES_FILES = {"project/decisions.md", "project/assumptions.md", "project/PM_NOTES.md"}


def _stats_mod():
    """Import the stats module (same folder) without breaking tests that stub it."""
    try:
        import stats as _st  # type: ignore
        return _st
    except Exception:  # noqa: BLE001
        return None


def resolve_notes_file(rel: str) -> Path | None:
    """Allow exactly project/decisions.md, project/assumptions.md,
    project/PM_NOTES.md and project/milestones/*.md (single .md file, no traversal)."""
    if not isinstance(rel, str) or not rel:
        return None
    norm = rel.replace("\\", "/")
    if norm in NOTES_FILES:
        try:
            base = (ROOT / "project").resolve()
            target = (ROOT / norm).resolve()
            if base not in target.parents and target != base:
                # decisions.md is directly under project/; allow parent == base
                if target.parent != base:
                    return None
            if target.suffix.lower() != ".md":
                return None
            return target
        except Exception:  # noqa: BLE001
            return None
    if norm.startswith("project/milestones/"):
        rest = norm[len("project/milestones/"):]
        if not rest or "/" in rest or "\\" in rest or ".." in rest:
            return None
        if not rest.endswith(".md") or rest.startswith("."):
            return None
        if not re.match(r"^[\w\-. ]+\.md$", rest):
            return None
        try:
            base = (ROOT / "project" / "milestones").resolve()
            target = (ROOT / norm).resolve()
            if target.parent != base:
                return None
            return target
        except Exception:  # noqa: BLE001
            return None
    return None


def build_info() -> dict:
    """{"exe", "exists", "mtime", "size_mb", "tag"}. Exe from play.bat else newest builds/*.exe."""
    exe = None
    try:
        play = read(ROOT / "play.bat")
        m = re.search(r"builds[\\/]([^\s\"'\)]+\.exe)", play, re.I)
        if m:
            exe = "builds/" + m.group(1).replace("\\", "/")
    except Exception:  # noqa: BLE001
        exe = None
    if not exe:
        try:
            cands = [p for p in (ROOT / "builds").glob("*.exe") if p.is_file()] if (ROOT / "builds").is_dir() else []
            if cands:
                best = max(cands, key=lambda p: p.stat().st_mtime)
                exe = "builds/" + best.name
        except OSError:
            pass
    exists, mtime, size_mb = False, "", 0.0
    if exe:
        try:
            p = ROOT / exe
            if p.is_file():
                exists = True
                st = p.stat()
                mtime = dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                size_mb = round(st.st_size / (1024 * 1024), 1)
        except OSError:
            exists = False
    tag = ""
    try:
        r = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], cwd=ROOT,
                           capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0:
            tag = (r.stdout or "").strip().splitlines()[0][:100] if (r.stdout or "").strip() else ""
    except Exception:  # noqa: BLE001
        tag = ""
    return {"exe": exe, "exists": exists, "mtime": mtime, "size_mb": size_mb, "tag": tag}


def opencode_snapshot() -> dict:
    with _opencode_lock:
        return {"days1": _opencode.get("days1"), "days7": _opencode.get("days7"),
                "error": _opencode.get("error"), "updated": _opencode.get("t", 0.0)}


def _run_opencode_once() -> None:
    st = _stats_mod()
    exe = shutil.which("opencode")
    if not exe:
        with _opencode_lock:
            _opencode.update({"days1": None, "days7": None, "error": "opencode not found"})
        return
    out: dict = {}
    err = None
    for key, days in (("days1", "1"), ("days7", "7")):
        try:
            r = subprocess.run([exe, "stats", "--days", days, "--models", "--project", ""], cwd=ROOT,
                               capture_output=True, text=True, timeout=60, encoding="utf-8",
                               errors="replace",
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                err = f"opencode exited {r.returncode}"
                out[key] = None
                continue
            parsed = st.parse_opencode_stats(r.stdout) if st else {"total": None, "models": {}}
            if parsed.get("total") is None and not parsed.get("models"):
                err = "could not parse opencode output"
            out[key] = parsed
        except Exception as e:  # noqa: BLE001
            err = str(e)[:200]
            out[key] = None
    with _opencode_lock:
        _opencode.update({"t": time.time(), "days1": out.get("days1"),
                          "days7": out.get("days7"),
                          "error": err if (out.get("days1") is None and out.get("days7") is None) else None})


def ensure_opencode() -> None:
    """Refresh opencode stats in a background thread at most every 10 min."""
    with _opencode_lock:
        stale = time.time() - float(_opencode.get("t", 0.0)) > 600
    if stale:
        threading.Thread(target=_run_opencode_once, daemon=True).start()


def cached_stats(hours: int) -> dict:
    st = _stats_mod()
    now = dt.datetime.now()
    key = (str(ROOT), hours)
    with _lock:
        ent = _stats_cache.get(key)
        if ent and time.time() - ent["t"] < 30:
            return ent["data"]
    data = st.build_stats(ROOT, now, hours) if st else {"hours": hours}
    try:
        data["codex"] = st.codex_usage() if st else None
    except Exception:  # noqa: BLE001
        data["codex"] = None
    try:
        data["paid_models"] = sorted(st._paid_models(ROOT)) if st and hasattr(st, "_paid_models") else []
    except Exception:  # noqa: BLE001
        data["paid_models"] = []
    ensure_opencode()
    data["opencode"] = opencode_snapshot()
    with _lock:
        _stats_cache[key] = {"t": time.time(), "data": data}
    return data


def process_status(commands: list[str], script: str) -> bool | None:
    """Absolute launch paths identify this project; old relative launches are ambiguous."""
    target = (ROOT / "orchestrator" / script).as_posix().lower()
    ambiguous = False
    for command in commands:
        command = command.replace("\\", "/").lower()
        if re.search(r'(?:^|[\s"\'])' + re.escape(target) + r'(?=$|[\s"\'])', command):
            return True
        if re.search(r'(?:^|[\s"\'])(?:\./)?orchestrator/' + re.escape(script) + r'(?=$|[\s"\'])', command):
            ambiguous = True
    return None if ambiguous else False


# ----------------------------------------------------------------------------- reading the project

def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------------------- manage mode (writes; --manage only)

def invalidate() -> None:
    """Drop the 2-second state cache so the next poll shows a write."""
    with _lock:
        _cache["t"] = 0.0


def atomic_write(p: Path, text: str) -> None:
    """Write a text file atomically: tmp beside it, then os.replace."""
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def flags_now() -> list:
    p = ROOT / "project"
    return [f for f in ("STOP", "RESTART", "PLAN_NOW") if (p / f).exists()]


def office_event(msg: str) -> None:
    with (ROOT / "project" / "events.log").open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")


# ----------------------------------------------------------------------------- settings (config.json editor)

def config_path() -> Path:
    return ROOT / "orchestrator" / "config.json"


def config_mtime() -> float:
    try:
        return config_path().stat().st_mtime
    except OSError:
        return 0.0


def read_config() -> dict | None:
    return read_json(config_path())


def _run_models_once() -> None:
    exe = shutil.which("opencode")
    if not exe:
        with _models_lock:
            _models.update({"t": time.time(), "data": []})
        return
    try:
        r = subprocess.run([exe, "models"], cwd=HERE, capture_output=True, text=True,
                           timeout=60, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise RuntimeError(f"opencode models exited {r.returncode}")
        out = r.stdout or ""
        found = sorted({m for m in re.findall(r"[\w./:@-]{1,100}", out) if "/" in m})
        with _models_lock:
            _models.update({"t": time.time(), "data": found})
    except Exception:  # noqa: BLE001
        with _models_lock:
            _models.update({"t": time.time(), "data": []})


def models_list() -> list:
    """`opencode models` output cached for 1 h, refreshed in a background thread."""
    with _models_lock:
        stale = time.time() - float(_models.get("t", 0.0)) > 3600
        data = list(_models.get("data") or [])
    if stale:
        threading.Thread(target=_run_models_once, daemon=True).start()
    return data


def agent_paid(cfg: dict, name: str) -> bool:
    return name in (cfg.get("paid_agents") or cfg.get("paid") or [])


def agent_kind(cfg: dict, name: str) -> str:
    a = (cfg.get("agents") or {}).get(name) or {}
    kind = a.get("kind")
    if kind:
        return kind
    cmd = a.get("cmd") or []
    return cmd[0] if cmd else "?"


def build_cmd_for_kind(kind: str, model: str, agents: dict) -> list | None:
    """New positions copy the cmd of an existing agent of the same kind (model replaced);
    with none of that kind, build it the way scaffold.py does."""
    for _n, a in agents.items():
        if (a or {}).get("kind") == kind and isinstance((a or {}).get("cmd"), list):
            cmd = list(a["cmd"])
            for flag in ("-m", "--model"):
                if flag in cmd:
                    cmd[cmd.index(flag) + 1] = model
                    return cmd
    if kind == "claude":
        return ["claude", "-p", "{prompt}", "--model", model, "--dangerously-skip-permissions"]
    if kind == "codex":
        return ["codex", "exec", "-m", model, "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check", "{prompt}", "{images}"]
    if kind == "opencode":
        return ["opencode", "run", "--auto", "--print-logs", "--log-level", "ERROR",
                "-m", model, "{prompt}"]
    return None


def set_model_in_cmd(cmd: list, model: str) -> list | None:
    """Replace only the value after -m / --model. None when the cmd has no such flag."""
    cmd = list(cmd)
    for flag in ("-m", "--model"):
        if flag in cmd:
            i = cmd.index(flag)
            if i + 1 < len(cmd):
                cmd[i + 1] = model
                return cmd
    return None


class ConfigError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def validate_whole_config(cfg: dict) -> None:
    """Every agent named in coders, paid_agents, roles, fallback chains and disabled_agents
    exists; chains have no duplicates; at least one coder; lanes within limits."""
    agents = cfg.get("agents") or {}
    if not isinstance(agents, dict):
        raise ConfigError(400, "agents must be an object")
    for name in cfg.get("coders") or []:
        if name not in agents:
            raise ConfigError(400, f"unknown coder {name}")
    if not (cfg.get("coders") or []):
        raise ConfigError(400, "at least one coder is required")
    for name in cfg.get("paid_agents") or cfg.get("paid") or []:
        if name not in agents:
            raise ConfigError(400, f"unknown paid agent {name}")
    for _role, name in (cfg.get("roles") or {}).items():
        if name not in agents:
            raise ConfigError(400, f"unknown role holder {name}")
    for name in cfg.get("disabled_agents") or []:
        if name not in agents:
            raise ConfigError(400, f"unknown disabled agent {name}")
    fb = cfg.get("fallback") or {}
    if not isinstance(fb, dict):
        raise ConfigError(400, "fallback must be an object")
    for key, chain in fb.items():
        if not isinstance(key, str) or ":" not in key:
            raise ConfigError(400, f"bad fallback key {key}")
        holder, _, step = key.partition(":")
        if holder not in agents:
            raise ConfigError(400, f"unknown fallback holder {holder}")
        if step not in FALLBACK_STEPS:
            raise ConfigError(400, f"bad fallback step {step}")
        if not isinstance(chain, list):
            raise ConfigError(400, f"bad fallback chain {key}")
        if len(set(chain)) != len(chain):
            raise ConfigError(400, f"duplicate agent in {key}")
        for member in chain:
            if member not in agents:
                raise ConfigError(400, f"unknown fallback agent {member}")
    lanes = cfg.get("lanes") or []
    if not isinstance(lanes, list):
        raise ConfigError(400, "lanes must be a list")
    if len(lanes) > 5:
        raise ConfigError(400, "at most 5 worktree lanes (6 total)")
    names = [str(e.get("name", "")).upper() for e in lanes if isinstance(e, dict)]
    if len(set(names)) != len(names):
        raise ConfigError(400, "duplicate lane names")
    for e in lanes:
        if not isinstance(e, dict) or not e.get("name") or not e.get("dir"):
            raise ConfigError(400, "lanes need {name, dir}")


def busy_agents() -> set:
    """Agents currently busy on a lane (per /api/state jobs)."""
    try:
        st = build_state()
    except Exception:  # noqa: BLE001
        return set()
    out = set()
    for job in st.get("jobs") or []:
        if job.get("agent"):
            out.add(job["agent"])
    return out


def busy_lane_letters() -> set:
    try:
        st = build_state()
    except Exception:  # noqa: BLE001
        return set()
    return {str(l.get("lane", "")).upper() for l in st.get("lanes") or [] if l.get("state") == "busy"}


def apply_config_changes(cfg: dict, changes: dict) -> tuple[dict, str, bool]:
    """Apply a changes dict to cfg (mutates a copy). Returns (new_cfg, summary, restart_needed).
    Raises ConfigError(code, msg)."""
    import copy
    if not isinstance(changes, dict):
        raise ConfigError(400, "changes must be an object")
    new = copy.deepcopy(cfg)
    new.setdefault("agents", {})
    agents = new["agents"]
    parts: list[str] = []
    restart = False

    for rid in changes.get("remove") or []:
        if rid not in agents:
            raise ConfigError(400, f"unknown agent {rid}")
        roles = new.get("roles") or {}
        if rid in roles.values():
            raise ConfigError(409, f"{rid} holds a role")
        if rid in (new.get("coders") or []) and len(new.get("coders") or []) <= 1:
            raise ConfigError(409, "cannot remove the only coder")
        if rid in busy_agents():
            raise ConfigError(409, f"{rid} is busy")
        del agents[rid]
        new["coders"] = [c for c in new.get("coders") or [] if c != rid]
        for key in ("paid_agents", "paid"):
            if key in new and isinstance(new[key], list):
                new[key] = [c for c in new[key] if c != rid]
        new["disabled_agents"] = [c for c in new.get("disabled_agents") or [] if c != rid]
        fb = new.get("fallback") or {}
        for key in list(fb):
            holder, _, _step = key.partition(":")
            if holder == rid:
                del fb[key]
            elif isinstance(fb[key], list) and rid in fb[key]:
                fb[key] = [c for c in fb[key] if c != rid]
        parts.append(f"remove {rid}")
        restart = True

    for spec in changes.get("add") or []:
        if not isinstance(spec, dict):
            raise ConfigError(400, "bad add spec")
        nid = spec.get("id", "")
        kind = spec.get("kind", "")
        model = spec.get("model", "")
        account = spec.get("account", "")
        label = spec.get("label", "")
        if not isinstance(nid, str) or not AGENT_ID_RE.match(nid):
            raise ConfigError(400, f"bad agent id {nid}")
        if nid in agents:
            raise ConfigError(400, f"duplicate agent id {nid}")
        if kind not in ("opencode", "claude", "codex"):
            raise ConfigError(400, f"bad kind {kind}")
        if not isinstance(model, str) or not MODEL_ID_RE.match(model):
            raise ConfigError(400, f"bad model id {model}")
        if not isinstance(account, str) or not ACCOUNT_ID_RE.match(account):
            raise ConfigError(400, f"bad account id {account}")
        if label is not None and (not isinstance(label, str) or len(label) > 40):
            raise ConfigError(400, "bad label")
        cmd = build_cmd_for_kind(kind, model, agents)
        if not cmd:
            raise ConfigError(400, f"cannot build cmd for kind {kind}")
        agents[nid] = {"cmd": cmd, "kind": kind, "model": model,
                       "account": account, "label": label or nid.replace("_", " ").title()}
        if kind == "opencode":
            agents[nid]["watch_rate_limit"] = True  # as scaffold.py: OpenCode retries limits silently
        parts.append(f"add {nid}")
        restart = True

    for aid, fields in (changes.get("agents") or {}).items():
        if aid not in agents:
            raise ConfigError(400, f"unknown agent {aid}")
        if not isinstance(fields, dict):
            raise ConfigError(400, f"bad fields for {aid}")
        a = agents[aid]
        if "model" in fields:
            model = fields["model"]
            if not isinstance(model, str) or not MODEL_ID_RE.match(model):
                raise ConfigError(400, f"bad model id {model}")
            cmd = a.get("cmd")
            if not isinstance(cmd, list) or set_model_in_cmd(cmd, model) is None:
                raise ConfigError(400, f"{aid} has no -m flag; model is read-only")
            a["cmd"] = set_model_in_cmd(cmd, model)
            a["model"] = model
            parts.append(f"model {aid}")
            restart = True
        if "account" in fields:
            account = fields["account"]
            if not isinstance(account, str) or not ACCOUNT_ID_RE.match(account):
                raise ConfigError(400, f"bad account id {account}")
            a["account"] = account
            parts.append(f"account {aid}")
            restart = True
        if "label" in fields:
            label = fields["label"]
            if not isinstance(label, str) or len(label) > 40:
                raise ConfigError(400, "bad label")
            a["label"] = label
            parts.append(f"label {aid}")
        if "coder" in fields:
            want = bool(fields["coder"])
            coders_now = list(new.get("coders") or [])
            if want and aid not in coders_now:
                coders_now.append(aid)
                parts.append(f"coder +{aid}")
                restart = True
            elif not want and aid in coders_now:
                if len(coders_now) <= 1:
                    raise ConfigError(409, "cannot remove the only coder")
                coders_now.remove(aid)
                parts.append(f"coder -{aid}")
                restart = True
            new["coders"] = coders_now
        if "paid" in fields:
            want = bool(fields["paid"])
            paid = list(new.get("paid_agents") or new.get("paid") or [])
            if want and aid not in paid:
                paid.append(aid)
                parts.append(f"paid +{aid}")
                restart = True
            elif not want and aid in paid:
                paid = [p for p in paid if p != aid]
                parts.append(f"paid -{aid}")
                restart = True
            new["paid_agents"] = paid
            new.pop("paid", None)

    if "coders" in changes:
        order = changes["coders"]
        if not isinstance(order, list) or set(order) != set(new.get("coders") or []) or len(order) != len(new.get("coders") or []):
            raise ConfigError(400, "bad coder order")
        for c in order:
            if c not in agents:
                raise ConfigError(400, f"unknown coder {c}")
        new["coders"] = list(order)
        parts.append("reorder coders")
        restart = True

    if "fallback" in changes:
        fb = changes["fallback"]
        if not isinstance(fb, dict):
            raise ConfigError(400, "bad fallback")
        new["fallback"] = {k: list(v) for k, v in fb.items()}
        parts.append("fallbacks")
        restart = True

    if "lanes" in changes:
        spec = changes["lanes"]
        if not isinstance(spec, dict) or "count" not in spec:
            raise ConfigError(400, "bad lanes")
        try:
            count = int(spec["count"])
        except (TypeError, ValueError):
            raise ConfigError(400, "bad lanes")
        if count < 1 or count > 6:
            raise ConfigError(400, "lanes must be 1-6")
        cur = list(new.get("lanes") or [])
        want_worktrees = max(0, count - 1)
        if len(cur) < want_worktrees:
            last_dir = cur[-1].get("dir", "") if cur else ""
            if last_dir:
                m = re.search(r"^(.*)([A-Za-z])$", last_dir.rstrip("/"))
                nxt = chr(ord("B") + len(cur))
                new_dir = (m.group(1) + nxt) if m else last_dir + nxt
            else:
                new_dir = spec.get("new_dir", "")
                if not new_dir or not os.path.isabs(new_dir):
                    raise ConfigError(400, "a dir is required (absolute path)")
                if "OneDrive" in new_dir:
                    raise ConfigError(400, "lane dirs must be outside OneDrive (Windows path limit and file locking)")
                nxt = chr(ord("B") + len(cur))
            for i in range(len(cur), want_worktrees):
                letter = chr(ord("B") + i)
                if i == len(cur) and not last_dir:
                    cur.append({"name": letter, "dir": new_dir})
                elif i == len(cur) and last_dir:
                    cur.append({"name": letter, "dir": new_dir})
                else:
                    prev = cur[-1]["dir"]
                    m2 = re.search(r"^(.*)([A-Za-z])$", prev.rstrip("/"))
                    nxt_dir = (m2.group(1) + letter) if m2 else prev + letter
                    cur.append({"name": letter, "dir": nxt_dir})
            void = spec.get("new_dir")
            if void and not last_dir and cur:
                if "OneDrive" in str(void):
                    raise ConfigError(400, "lane dirs must be outside OneDrive (Windows path limit and file locking)")
            parts.append(f"lanes {1 + len(new.get('lanes') or [])}→{count}")
        elif len(cur) > want_worktrees:
            if len(cur) - want_worktrees > 0:
                last = cur[-1].get("name", "").upper()
                if last in busy_lane_letters():
                    raise ConfigError(409, f"lane {last} is busy")
                cur = cur[:want_worktrees]
            parts.append(f"lanes {1 + len(new.get('lanes') or [])}→{count}")
        new["lanes"] = cur
        restart = True

    if "approval_gate" in changes:
        ag = changes["approval_gate"]
        if not isinstance(ag, dict):
            raise ConfigError(400, "bad approval_gate")
        gate = {"enabled": bool(ag.get("enabled", False)),
                "types": list(ag.get("types") or []),
                "workers": list(ag.get("workers") or []),
                "timeout_minutes": ag.get("timeout_minutes", 0)}
        try:
            gate["timeout_minutes"] = float(gate["timeout_minutes"] or 0)
        except (TypeError, ValueError):
            raise ConfigError(400, "bad timeout_minutes")
        for w in gate["workers"]:
            if w not in agents:
                raise ConfigError(400, f"unknown gate worker {w}")
        new["approval_gate"] = gate
        parts.append("approval gate")
        restart = True

    if "spend_cap" in changes:
        sc = changes["spend_cap"]
        if not isinstance(sc, dict):
            raise ConfigError(400, "bad spend_cap")
        try:
            daily = float(sc.get("daily_usd", 0) or 0)
        except (TypeError, ValueError):
            raise ConfigError(400, "bad daily_usd")
        members = list(sc.get("agents") or [])
        for m in members:
            if m not in agents:
                raise ConfigError(400, f"unknown spend cap agent {m}")
        new["spend_cap"] = {"daily_usd": daily, "agents": members}
        parts.append("spend cap")
        restart = True

    # Whole-config validation: every reference must still resolve.
    try:
        validate_whole_config(new)
    except ConfigError:
        raise
    # Extra removal rule: an agent referenced in a chain must also be removed from the chain.
    # apply_config_changes already cleans chains on remove; a direct fallback edit that drops an
    # agent definition without cleaning is caught by validate_whole_config (unknown agent).
    # But removing the only coder / a role holder / a chain member without cleaning via a raw
    # fallback+agents edit is refused here when inconsistent.
    return new, ", ".join(parts) or "no changes", restart


def write_config_file(new_cfg: dict, raw_before: str) -> float:
    """Backup (newest 20), atomic write with indent=2. Returns the new mtime."""
    backup_dir = config_path().parent / "config.backups"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (backup_dir / f"config-{stamp}.json").write_text(raw_before, encoding="utf-8")
        existing = sorted(backup_dir.glob("config-*.json"), key=lambda p: p.name)
        for old in existing[:-20]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass
    text = json.dumps(new_cfg, indent=2)
    tmp = config_path().with_name(config_path().name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, config_path())
    try:
        ts = config_mtime()
        os.utime(config_path(), (ts, ts))
    except OSError:
        pass
    return config_mtime()


# ----------------------------------------------------------------------------- approvals (human-in-the-loop gate)

def approvals_dir() -> Path:
    return ROOT / "project" / "approvals"


def list_approvals() -> list:
    """Pending approval requests (read-only)."""
    d = approvals_dir()
    out = []
    try:
        files = sorted(d.glob("*.json")) if d.is_dir() else []
    except OSError:
        return []
    for p in files:
        if p.name.endswith(".decision.json") or (d / "done" / p.name).exists():
            continue
        if (d / f"{p.stem}.decision.json").exists():
            continue
        try:
            req = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(req, dict):
            out.append(req)
    return out


def host_allowed(host: str) -> bool:
    """DNS-rebinding guard: only localhost (or the LAN IP with --lan) may use the API in manage mode."""
    name = (host or "").strip().lower()
    if name.startswith("["):  # IPv6 literal [::1]:port
        name = name.split("]")[0] + "]"
    elif name.count(":") == 1 and name.rsplit(":", 1)[1].isdigit():
        name = name.rsplit(":", 1)[0]
    ok = {"localhost", "127.0.0.1", "::1"}
    if LAN_IP:
        ok.add(LAN_IP.lower())
    return name in ok


def token_ok(given: str | None) -> bool:
    return bool(given) and bool(TOKEN) and hmac.compare_digest(given, TOKEN)


def parse_requests(text: str) -> dict:
    """OWNER_REQUESTS.md -> {"open": [...], "handled": [...]}. Items are bullets or plain
    paragraphs under ## Open / ## Handled; (none...) placeholders are skipped."""
    open_items: list = []
    handled_items: list = []
    cur: str | None = None
    para: list = []

    def is_none(s: str) -> bool:
        return s.strip().lower().startswith("(none")

    def flush() -> None:
        if para:
            item = " ".join(para).strip()
            if item and not is_none(item):
                (open_items if cur == "open" else handled_items).append(item)
            para.clear()

    for line in text.splitlines():
        m = re.match(r"^##\s+(\S.*?)\s*$", line)
        if m:
            flush()
            head = m.group(1).lower()
            cur = "open" if head == "open" else "handled" if head == "handled" else None
            continue
        if cur is None:
            continue
        if not line.strip():
            flush()
            continue
        b = re.match(r"^\s*[-*]\s+(.*)$", line)
        if b:
            flush()
            if b.group(1).strip() and not is_none(b.group(1)):
                (open_items if cur == "open" else handled_items).append(b.group(1).strip())
        else:
            para.append(line.strip())
    flush()
    return {"open": open_items, "handled": handled_items}


def insert_request(raw: str, entry: str) -> str:
    """Insert an `- ...` entry line as the last item under ## Open, replacing a (none)
    placeholder if there is one. Everything else stays byte-for-byte identical."""
    if not re.search(r"^##\s+Open\s*$", raw, re.M):
        if raw and not raw.endswith("\n"):
            raw += "\n"
        return (raw + "\n## Open\n\n" + entry + "\n") if raw else ("# Owner Requests\n\n## Open\n\n" + entry + "\n")
    lines = raw.split("\n")
    hi = next(i for i, l in enumerate(lines) if re.match(r"^##\s+Open\s*$", l))
    end = next((i for i in range(hi + 1, len(lines)) if re.match(r"^##\s+", lines[i])), len(lines))
    seg = lines[hi + 1:end]
    for i, s in enumerate(seg):
        if s.strip().lower().startswith("(none"):
            seg[i] = entry
            return "\n".join(lines[:hi + 1] + seg + lines[end:])
    idx = len(seg)
    while idx > 0 and not seg[idx - 1].strip():
        idx -= 1
    seg.insert(idx, entry)
    return "\n".join(lines[:hi + 1] + seg + lines[end:])


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        else:
            proc.kill()
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def run_probe_one(name: str, agent: dict) -> None:
    """Run one agent's cmd with {prompt} replaced; record ok/fail/timeout into _probe."""
    t0 = time.time()
    state_, detail = "fail", ""
    try:
        cmd = agent.get("cmd") or []
        prompt = "Reply with exactly: OK"
        if isinstance(cmd, str):
            argv = shlex.split(cmd.replace("{prompt}", prompt))
        else:
            argv = [c.replace("{prompt}", prompt) for c in cmd]
        argv[0] = shutil.which(argv[0]) or argv[0]  # npm CLIs are .cmd shims that Popen can't find by bare name
        env = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1")
        proc = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
        try:
            out, _ = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            out, _ = proc.communicate()
            raise TimeoutError("probe timed out")
        detail = (out or "")[-200:]
        state_ = "ok" if proc.returncode == 0 and "OK" in (out or "") else "fail"
    except TimeoutError:
        state_ = "timeout"
    except Exception as e:  # noqa: BLE001
        detail = repr(e)[-200:]
    with _probe_lock:
        _probe["results"][name] = {"state": state_, "seconds": round(time.time() - t0, 2), "detail": detail}


def run_probe_all(agents: dict) -> None:
    """Agents sharing an account run one after another; different accounts run in parallel."""
    groups: dict = {}
    for n, a in agents.items():
        groups.setdefault((a or {}).get("account", n), []).append(n)
    threads = []
    for names in groups.values():
        t = threading.Thread(target=lambda ns=names: [run_probe_one(n, agents[n]) for n in ns], daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    with _probe_lock:
        _probe["running"] = False


def watch_processes() -> None:
    """Background thread: is an orchestrator / supervisor running? (A PowerShell query takes a few seconds.)"""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
          "ForEach-Object { $_.CommandLine }")
    while True:
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 timeout=15, check=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            commands = out.splitlines()
            _procs["orchestrator"] = process_status(commands, "orchestrator.py")
            _procs["supervisor"] = process_status(commands, "supervisor.py")
        except Exception:  # noqa: BLE001
            _procs["orchestrator"] = _procs["supervisor"] = None
        _procs["checked"] = time.time()
        time.sleep(20)


def parse_time(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


EVENT_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+(.*)$")


def classify(text: str) -> dict:
    """Event line -> {kind, task, lane} for the page's animations and ticker."""
    m = re.match(r"DONE (T-\d+) \(attempt \d+, lane (\w)\)", text)
    if m:
        return {"kind": "done", "task": m.group(1), "lane": m.group(2)}
    m = re.match(r"START (T-\d+) \[lane (\w)\]", text)
    if m:
        return {"kind": "start", "task": m.group(1), "lane": m.group(2)}
    m = re.match(r"LANE (\w) merged (T-\d+)", text)
    if m:
        return {"kind": "merged", "task": m.group(2), "lane": m.group(1)}
    m = re.match(r"BLOCKED (T-\d+)", text)
    if m:
        return {"kind": "blocked", "task": m.group(1)}
    m = re.match(r"(T-\d+) a\d+ (WORK|CHECKS|QA|REVIEW) (\w+)", text)
    if m:
        return {"kind": m.group(2).lower() + "_" + m.group(3).lower(), "task": m.group(1)}
    for prefix, kind in (("MILESTONE", "milestone"), ("PROJECT COMPLETE", "complete"), ("PLAN start", "plan_start"),
                         ("PLAN done", "plan_done"), ("USAGE LIMIT", "limit"), ("QUOTA RESTORED", "restored"),
                         ("FALLBACK", "fallback"), ("SUPERVISOR", "supervisor"), ("PROVIDER DOWN", "limit"),
                         ("PREEMPTIVE HANDOFF", "limit"), ("MODEL GONE", "gone"), ("SPEND CAP", "limit"),
                         ("BENCH", "bench"), ("UNBENCH", "bench"), ("APPROVAL WAIT", "approval"),
                         ("APPROVAL TIMEOUT", "approval"), ("APPROVAL", "approval"),
                         ("RESTART", "restart"), ("ORCHESTRATOR START", "boot")):
        if text.startswith(prefix):
            return {"kind": kind}
    return {"kind": "other"}


def newest_log(folder: Path, step: str | None, agents: dict) -> str | None:
    """The agent behind the newest `<step>.<agent>.log` in a run folder (the one running now, or the last one)."""
    best, best_t = None, -1.0
    try:
        files = list(folder.glob("*.log"))
    except OSError:
        return None
    for f in files:
        if f.name.endswith(".live.log"):
            continue
        m = re.match(r"^(\w+)\.(\w+)\.log$", f.name)
        if not m or m.group(2) not in agents or (step and m.group(1) != step):
            continue
        try:
            t = f.stat().st_mtime
        except OSError:
            continue
        if t > best_t:
            best, best_t = m.group(2), t
    return best


def agent_labels(agents: dict) -> dict:
    """label -> agent, from config.json labels and (for older projects) the AGENT_NAMES table in orchestrator.py."""
    out = {a.get("label", n): n for n, a in agents.items()}
    src = read(ROOT / "orchestrator" / "orchestrator.py")
    m = re.search(r"^AGENT_NAMES = \{(.*?)\}\s*$", src, re.M | re.S)
    if m:
        for name, label in re.findall(r'"(\w+)":\s*"([^"]+)"', m.group(1)):
            if name in agents:
                out[label] = name
    return out


def agent_from_activity(activity: str, labels: dict) -> str | None:
    """'<label> working on <step>' names the agent the orchestrator just started (longest label wins)."""
    head = activity.split(" working on ")[0] if " working on " in activity else ""
    return labels.get(head) or next((labels[l] for l in sorted(labels, key=len, reverse=True) if head.startswith(l)), None)


def latest_attempt(tid: str) -> Path | None:
    d = ROOT / "project" / "runs" / tid
    try:
        attempts = sorted((p for p in d.iterdir() if re.match(r"a\d+$", p.name)), key=lambda p: int(p.name[1:]))
    except OSError:
        return None
    return attempts[-1] if attempts else None


def lane_log_for(tid: str) -> str | None:
    """Repo-relative log path for a running task: the .live.log if one exists,
    otherwise the newest <step>.<agent>.log in the latest attempt, else None."""
    try:
        folder = latest_attempt(tid)
        if not folder:
            return None
        try:
            live = [p for p in folder.glob("*.live.log") if p.is_file()]
        except OSError:
            live = []
        if live:
            def _mt(p: Path) -> float:
                try:
                    return p.stat().st_mtime
                except OSError:
                    return -1.0
            best = max(live, key=_mt)
            try:
                return best.relative_to(ROOT).as_posix()
            except ValueError:
                return None
        try:
            logs = [p for p in folder.glob("*.log")
                    if p.is_file() and not p.name.endswith(".live.log")
                    and re.match(r"^(\w+)\.(\w+)\.log$", p.name)]
        except OSError:
            logs = []
        if not logs:
            return None
        best = max(logs, key=_mt)
        try:
            return best.relative_to(ROOT).as_posix()
        except ValueError:
            return None
    except Exception:  # noqa: BLE001
        return None


def truncate_strings(obj, limit: int = 4000):
    """Truncate long strings inside parsed JSON with an ellipsis."""
    if isinstance(obj, str):
        return obj[:limit] + "…" if len(obj) > limit else obj
    if isinstance(obj, dict):
        return {k: truncate_strings(v, limit) for k, v in obj.items()}
    if isinstance(obj, list):
        return [truncate_strings(v, limit) for v in obj]
    return obj


def board_summary() -> dict:
    board = read_json(ROOT / "project" / "board.json") or {}
    tasks = []
    for t in board.get("tasks", []):
        if not isinstance(t, dict):
            continue
        tasks.append({
            "id": t.get("id", ""), "title": t.get("title", ""), "status": t.get("status", ""),
            "milestone": t.get("milestone", ""), "priority": t.get("priority", 3),
            "type": t.get("type", ""), "owner": t.get("owner", ""),
            "depends_on": list(t.get("depends_on", []) or []),
            "attempts": t.get("attempts", 0),
        })
    ms_ids = sorted({t.get("milestone", "") for t in board.get("tasks", []) if t.get("milestone")},
                    key=lambda m: (int(re.sub(r"\D", "", m) or 0), m))
    return {"tasks": tasks, "milestones": ms_ids}


def task_detail(tid: str) -> dict | None:
    board = read_json(ROOT / "project" / "board.json") or {}
    task = next((t for t in board.get("tasks", []) if isinstance(t, dict) and t.get("id") == tid), None)
    if task is None:
        return None
    brief = read(ROOT / "project" / "tasks" / f"{tid}.md")
    runs_dir = ROOT / "project" / "runs" / tid
    detailed = []
    try:
        sub = sorted((p for p in runs_dir.iterdir() if p.is_dir() and re.match(r"a\d+$", p.name)),
                     key=lambda p: int(p.name[1:])) if runs_dir.is_dir() else []
    except OSError:
        sub = []
    for folder in sub:
        n = int(folder.name[1:])
        files = []
        try:
            entries = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name)
        except OSError:
            entries = []
        for f in entries:
            suf = f.suffix.lower()
            kind = "json" if suf == ".json" else "log" if suf == ".log" else "image" if suf == ".png" \
                else "patch" if suf == ".patch" else "other"
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            files.append({"name": f.name, "size": size, "kind": kind})
        work = truncate_strings(read_json(folder / "work.json")) if (folder / "work.json").is_file() else None
        qa = truncate_strings(read_json(folder / "qa.json")) if (folder / "qa.json").is_file() else None
        review = truncate_strings(read_json(folder / "review.json")) if (folder / "review.json").is_file() else None
        detailed.append({"n": n, "files": files, "work": work, "qa": qa, "review": review})
    out = dict(task)
    out["attempts_count"] = task.get("attempts", 0)
    out["brief"] = brief
    out["attempts"] = detailed
    return out


def resolve_office_file(rel: str) -> Path | None:
    """Repo-relative path -> resolved Path if inside project/runs or project/tasks
    with an allowed suffix; otherwise None (403). Beats .., absolute paths, symlinks."""
    if not isinstance(rel, str) or not rel:
        return None
    if re.match(r"^[a-zA-Z]:", rel) or rel.startswith("\\\\") or rel.startswith("/"):
        return None
    try:
        if Path(rel).is_absolute():
            return None
    except Exception:  # noqa: BLE001
        return None
    p = Path(rel)
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        return None
    try:
        target = (ROOT / rel).resolve()
        base_runs = (ROOT / "project" / "runs").resolve()
        base_tasks = (ROOT / "project" / "tasks").resolve()
    except Exception:  # noqa: BLE001
        return None
    try:
        target.relative_to(base_runs)
        inside = True
    except ValueError:
        try:
            target.relative_to(base_tasks)
            inside = True
        except ValueError:
            inside = False
    if not inside:
        return None
    return target


def screenshots_list() -> list:
    with _lock:
        if time.time() - _shots["t"] < 10 and _shots["data"] is not None:
            return _shots["data"]
    board = read_json(ROOT / "project" / "board.json") or {}
    titles = {t.get("id"): t.get("title", "") for t in board.get("tasks", []) if isinstance(t, dict)}
    runs = ROOT / "project" / "runs"
    found = []
    try:
        paths = list(runs.glob("T-*/a*/*.png")) if runs.is_dir() else []
    except OSError:
        paths = []
    for p in paths:
        if not p.is_file():
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        try:
            rel = p.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        parts = p.relative_to(runs).parts
        task = parts[0] if len(parts) > 0 else ""
        attempt = parts[1] if len(parts) > 1 else ""
        found.append({"task": task, "attempt": attempt, "name": p.name, "path": rel,
                      "t": dt.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M"),
                      "title": titles.get(task, ""), "_mt": mt})
    found.sort(key=lambda e: e.pop("_mt"))
    with _lock:
        _shots["t"] = time.time()
        _shots["data"] = found
    return found


def validate_command(data: dict, board: dict) -> tuple[int, str]:
    """(code, error). 0 means valid. Mirrors the orchestrator inbox rules."""
    action = data.get("action", "")
    if action not in ("set_priority", "set_status", "retry", "add_task",
                      "bench", "unbench", "set_approval"):
        return 400, "unknown action"
    if action in ("bench", "unbench"):
        ag = data.get("agent")
        if not isinstance(ag, str) or not ag:
            return 400, "agent required"
        return 0, ""
    if action == "set_approval":
        tid, req = data.get("task"), data.get("required")
        if not isinstance(tid, str) or not TASK_ID_RE.match(tid):
            return 400, "bad task"
        if not next((t for t in board.get("tasks", []) if t.get("id") == tid), None):
            return 400, "unknown task"
        if not isinstance(req, bool):
            return 400, "bad required"
        return 0, ""
    if action == "set_priority":
        tid, prio = data.get("task"), data.get("priority")
        if not isinstance(tid, str) or prio is None:
            return 400, "task and priority required"
        if not TASK_ID_RE.match(tid) or not next((t for t in board.get("tasks", []) if t.get("id") == tid), None):
            return 400, "unknown task"
        try:
            if isinstance(prio, bool):
                raise ValueError()
            p = int(prio)
        except Exception:  # noqa: BLE001
            return 400, "bad priority"
        if p < 1 or p > 5:
            return 400, "bad priority"
        return 0, ""
    if action == "set_status":
        tid, st = data.get("task"), data.get("status")
        if not isinstance(tid, str) or not isinstance(st, str):
            return 400, "task and status required"
        if not TASK_ID_RE.match(tid) or not next((t for t in board.get("tasks", []) if t.get("id") == tid), None):
            return 400, "unknown task"
        if st not in ("backlog", "ready", "dropped"):
            return 400, "bad status"
        t = next((x for x in board.get("tasks", []) if x.get("id") == tid), {})
        if t.get("status") in ("in_progress", "done"):
            return 409, f"task is {t.get('status')}"
        return 0, ""
    if action == "retry":
        tid = data.get("task")
        if not isinstance(tid, str):
            return 400, "task required"
        t = next((x for x in board.get("tasks", []) if x.get("id") == tid), None)
        if not t or not TASK_ID_RE.match(tid):
            return 400, "unknown task"
        if t.get("status") != "blocked":
            return 409, "only blocked tasks can be retried"
        return 0, ""
    spec = data.get("task")
    if not isinstance(spec, dict):
        return 400, "task spec required"
    if not isinstance(spec.get("title"), str) or not spec["title"].strip():
        return 400, "bad title"
    if "type" in spec and spec["type"] not in ("code", "asset", "design", "qa"):
        return 400, "bad type"
    if "priority" in spec:
        try:
            p = spec["priority"]
            if isinstance(p, bool):
                raise ValueError()
            p = int(p)
            if p < 1 or p > 5:
                raise ValueError()
        except Exception:  # noqa: BLE001
            return 400, "bad priority"
    if "acceptance" in spec and (not isinstance(spec["acceptance"], list)
                                 or not all(isinstance(x, str) for x in spec["acceptance"])):
        return 400, "bad acceptance"
    if "depends_on" in spec and (not isinstance(spec["depends_on"], list)
                                 or not all(isinstance(x, str) for x in spec["depends_on"])):
        return 400, "bad depends_on"
    return 0, ""


def step_of(activity: str) -> str:
    a = activity.lower()
    m = re.search(r"working on (\w+)", a)
    if m:
        return m.group(1)
    if "running godot checks" in a:
        return "checks"
    if "merge" in a:
        return "merge"
    if "sleeping until" in a:
        return "sleeping"
    if a.startswith("stopped"):
        return "stopped"
    return "other"


def limits(events: list[str], agents: dict) -> dict:
    """agent -> {state: limited|down|gone, until}, for limits still in force."""
    account = {n: a.get("account", n) for n, a in agents.items()}
    out: dict = {}
    now = dt.datetime.now()
    for line in events:
        m = re.match(r"(\S+ \S+)\s+(USAGE LIMIT|SPEND CAP|PROVIDER DOWN|MODEL GONE|PREEMPTIVE HANDOFF|QUOTA RESTORED|BENCH|UNBENCH) ([\w-]+)", line)
        if not m:
            continue
        when = parse_time(m.group(1))
        if not when:
            continue
        if m.group(2) == "QUOTA RESTORED":
            out = {k: v for k, v in out.items() if account.get(k) != m.group(3) and k != m.group(3)}
            continue
        if m.group(2) in ("BENCH", "UNBENCH"):
            continue  # bench state comes from config.json, not events
        u = re.search(r"until ~?(?:\w{3} )?(\d{1,2}):(\d{2})", line)
        until = when.replace(hour=int(u.group(1)), minute=int(u.group(2)), second=0) if u else when + dt.timedelta(hours=1)
        if until < when:
            until += dt.timedelta(days=1)
        kind = {"USAGE LIMIT": "limited", "SPEND CAP": "limited", "PREEMPTIVE HANDOFF": "limited",
                "PROVIDER DOWN": "down", "MODEL GONE": "gone"}[m.group(2)]
        subject = m.group(3)
        if kind == "limited":  # handoffs name an account; usage limits name an agent
            acct = account.get(subject, subject)
            for other, other_acct in account.items():
                if other_acct == acct:
                    out[other] = {"state": kind, "until": until}
        elif subject in agents:
            out[subject] = {"state": kind, "until": until}
    return {k: {"state": v["state"], "until": v["until"].strftime("%H:%M")} for k, v in out.items() if v["until"] > now}


def build_state() -> dict:
    p = ROOT / "project"
    cfg = read_json(ROOT / "orchestrator" / "config.json") or {}
    agents = cfg.get("agents") or {}
    board = read_json(p / "board.json") or {}
    status = read(p / "STATUS.md")
    all_events = read(p / "events.log").splitlines()
    tail = all_events[-800:]

    tasks = {t["id"]: t for t in board.get("tasks", [])}
    updated = parse_time((re.search(r"^Updated: (.+)$", status, re.M) or [None, ""])[1].strip())
    finished = {}  # task -> time it was DONE / BLOCKED (to correct a STATUS.md that hasn't been rewritten yet)
    for line in tail:
        m = re.match(r"(\S+ \S+)\s+(?:DONE|BLOCKED) (T-\d+)", line)
        if m:
            finished[m.group(2)] = parse_time(m.group(1))

    labels = agent_labels(agents)
    jobs = []  # what each agent is doing right now: {agent, station, lane, task, title, step, type}

    def lane_job(lane: str, task_text: str, activity: str) -> dict:
        m = re.match(r"^(T-\d+)\s+(.*?)(?:\s+\((\w+)\))?$", task_text.strip())
        if not m:
            return {"lane": lane, "state": "idle", "activity": activity, "log": None}
        tid, title = m.group(1), m.group(2)
        if tid in finished and updated and finished[tid] and finished[tid] >= updated:
            return {"lane": lane, "state": "idle", "activity": "finished " + tid, "log": None}
        step = step_of(activity)
        agent = agent_from_activity(activity, labels)
        if not agent and step not in ("checks", "merge", "sleeping", "stopped"):
            folder = latest_attempt(tid)
            if folder:
                agent = newest_log(folder, step if step in ("work", "qa", "review") else None, agents)
        t = tasks.get(tid, {})
        return {"lane": lane, "state": "busy", "task": tid, "title": title, "step": step, "agent": agent,
                "type": t.get("type", ""), "owner": t.get("owner", ""), "milestone": t.get("milestone", ""),
                "attempt": t.get("attempts", 0), "activity": activity, "log": lane_log_for(tid)}

    now_text = (re.search(r"^\*\*Now:\*\* (.*)$", status, re.M) or [None, ""])[1]
    cur = (re.search(r"^\*\*Current task:\*\* (.*)$", status, re.M) or [None, "-"])[1]
    lane_names = ["A"] + [ln.get("name", "?") for ln in cfg.get("lanes", [])]
    lanes = {}
    planner = {"busy": False}
    if "working on plan" in now_text and cur.strip() in ("-", ""):
        planner = {"busy": True, "reason": "", "activity": now_text}
        lanes["A"] = {"lane": "A", "state": "idle", "activity": "planning", "log": None}
    else:
        lanes["A"] = lane_job("A", cur if cur.strip() != "-" else "", now_text)
    for name, text in re.findall(r"^\*\*Lane (\w+):\*\* (.*)$", status, re.M):
        if text.strip() == "idle" or text.strip() == "off":
            lanes[name] = {"lane": name, "state": "idle", "activity": "", "log": None}
            continue
        m = re.match(r"^(T-\d+ .*?\(\w+\))(?: - (.*))?$", text)
        lanes[name] = lane_job(name, m.group(1), m.group(2) or "") if m else {"lane": name, "state": "idle", "activity": text, "log": None}
    pl = re.search(r"^\*\*Planner:\*\* (.*?)(?: \((.*)\))?$", status, re.M)
    if pl:
        planner = {"busy": True, "activity": pl.group(1), "reason": pl.group(2) or ""}
    if planner["busy"]:
        runs = sorted((p / "runs" / "_plan").glob("*"), key=lambda q: q.name)
        planner["agent"] = (agent_from_activity(planner.get("activity", ""), labels) or agent_from_activity(now_text, labels)
                            or (newest_log(runs[-1], "plan", agents) if runs else None) or "claude")
        jobs.append({"agent": planner["agent"], "station": "plan", "step": "plan", "task": "",
                     "title": planner.get("reason") or "planning the next tasks"})
    for name in lane_names:
        ln = lanes.get(name) or {"lane": name, "state": "idle", "log": None}
        if "log" not in ln:
            ln["log"] = lane_log_for(ln["task"]) if ln.get("state") == "busy" and ln.get("task") else None
        lanes[name] = ln
        if ln["state"] == "busy" and ln.get("agent") and ln.get("step") in ("work", "qa", "review"):
            jobs.append({"agent": ln["agent"], "station": f"lane:{name}", "step": ln["step"], "task": ln["task"],
                         "title": ln["title"], "type": ln.get("type", "")})

    # Supervisor's AI fixer: "SUPERVISOR-AI <agent> called" without a later done/timed out/unavailable/finished.
    fixer = None
    for line in tail:
        m = re.search(r"SUPERVISOR-AI (\w+) (called|done|timed out|unavailable|finished)", line)
        if m:
            fixer = m.group(1) if m.group(2) == "called" else None
    if fixer and fixer in agents:
        jobs.append({"agent": fixer, "station": "boss", "step": "fix", "task": "", "title": "fixing a stall for the supervisor"})
    last_sup = next((EVENT_RE.match(l).group(2) for l in reversed(tail) if "SUPERVISOR" in l and EVENT_RE.match(l)), "")

    lim = limits(tail, agents)
    benched_set = set(cfg.get("disabled_agents") or [])
    agent_list = []
    for n, a in agents.items():
        kind = (a.get("cmd") or ["?"])[0]
        label = a.get("label") or next((l for l, x in labels.items() if x == n and l != n), n)
        agent_list.append({"id": n, "label": label, "tool": kind, "model": a.get("model", ""),
                           "kind": a.get("kind", kind), "account": a.get("account", n),
                           "paid": n in (cfg.get("paid_agents") or cfg.get("paid") or []),
                           "coder": n in (cfg.get("coders") or []),
                           "benched": n in benched_set,
                           **({"limit": lim[n]} if n in lim else {})})

    # Subscriptions (usage-limit buckets): every account in play, worst state first. Shared by
    # every position on the account, so two roles on one model nap and recover together.
    acct_labels = cfg.get("accounts") or {}
    acct_members: dict = {}
    for n, a in agents.items():
        acct_members.setdefault(a.get("account", n), []).append(n)
    sev = {"gone": 3, "down": 2, "limited": 1}
    accounts = []
    for acct, members in acct_members.items():
        hits = [(m, lim[m]) for m in members if m in lim]
        if hits:
            m, l = max(hits, key=lambda h: (sev.get(h[1]["state"], 0), h[1].get("until", "")))
            accounts.append({"id": acct, "label": acct_labels.get(acct, acct),
                             "state": l["state"], "until": l["until"], "agents": members})
        else:
            accounts.append({"id": acct, "label": acct_labels.get(acct, acct), "state": "ok", "agents": members})
    accounts.sort(key=lambda x: (sev.get(x.get("state"), 0), x["id"]), reverse=True)

    # Milestones: done (+dropped) / total from the board; title from the close-out report if there is one.
    ms: dict = {}
    for t in board.get("tasks", []):
        m = ms.setdefault(t["milestone"], {"id": t["milestone"], "done": 0, "total": 0, "blocked": 0, "active": 0})
        m["total"] += 1
        m["done"] += t["status"] in ("done", "dropped")
        m["blocked"] += t["status"] == "blocked"
        m["active"] += t["status"] == "in_progress"
    order = sorted(ms.values(), key=lambda m: int(re.sub(r"\D", "", m["id"]) or 0))
    for m in order:
        head = read(p / "milestones" / f"{m['id']}.md").splitlines()[:1]
        mm = re.match(r"#\s*M\d+[^:]*:\s*(.*)", head[0]) if head else None
        m["title"] = mm.group(1).strip() if mm else ""
    order = [m for m in order if m["total"] > 0]

    events = []
    last = tail[-60:]
    start = len(all_events) - len(last)  # event ids are line numbers, so the page can spot new ones
    for i, line in enumerate(last):
        m = EVENT_RE.match(line)
        if m:
            events.append({"id": start + i,
                           "t": m.group(1)[11:16], "text": m.group(2)[:220], **classify(m.group(2))})

    flags = [f for f in ("STOP", "RESTART", "PLAN_NOW") if (p / f).exists()]
    game = (re.search(r"^# (.+?): Live Status", status, re.M) or [None, board.get("project") or ROOT.name])[1]
    try:
        pending_approvals = list_approvals()
    except Exception:  # noqa: BLE001
        pending_approvals = []
    return {
        "game": game, "time": dt.datetime.now().strftime("%H:%M"), "updated": updated.strftime("%H:%M") if updated else "",
        "orchestrator": _procs["orchestrator"], "supervisor": _procs["supervisor"], "flags": flags,
        "now": now_text, "lanes": [lanes[n] for n in lane_names], "planner": planner, "jobs": jobs,
        "agents": agent_list, "accounts": accounts, "milestones": order, "events": events, "supervisor_msg": last_sup[:200],
        "complete": bool(board.get("project_complete")),
        "configured": bool(agents), "demo": False, "manage": MANAGE,
        "approvals": pending_approvals,
        "approval_wait": [r.get("task", "") for r in pending_approvals if r.get("task")],
        "counts": {s: sum(1 for t in board.get("tasks", []) if t["status"] == s)
                   for s in ("done", "in_progress", "ready", "backlog", "blocked")},
    }


def state() -> dict:
    with _lock:
        if time.time() - _cache["t"] > 2 or _cache["state"] is None:
            try:
                _cache["state"] = build_state()
            except Exception as e:  # noqa: BLE001  (a half-written file must never kill the page)
                _cache["state"] = {**(_cache["state"] or {}), "error": repr(e)[:300]}
            _cache["t"] = time.time()
        return _cache["state"]


# ----------------------------------------------------------------------------- web server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:  # keep the console quiet
        pass

    def send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def deny(self, code: int, msg: str) -> None:
        self.send(code, json.dumps({"error": msg}).encode("utf-8"), "application/json")

    def check_manage(self) -> bool:
        """Host + manage-mode + token guard for writes and manage-only GETs. True if allowed."""
        if MANAGE and not host_allowed(self.headers.get("Host", "")):
            self.deny(403, "bad host")
            return False
        if not MANAGE:
            self.deny(403, "manage mode off")
            return False
        if not token_ok(self.headers.get("X-Office-Token")):
            self.deny(403, "bad token")
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        path = unquote(url.path)
        qs = parse_qs(url.query)
        if path == "/api/state":
            if DEMO:
                from demo import demo_state
                scene = qs.get("scene", ["auto"])[0]
                st = demo_state(scene)
                st["manage"] = True  # the demo shows the manage UI off
                return self.send(200, json.dumps(st).encode("utf-8"), "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            return self.send(200, json.dumps(state()).encode("utf-8"), "application/json")
        if path == "/api/board":
            if DEMO:
                from demo import demo_board
                return self.send(200, json.dumps(demo_board()).encode("utf-8"),
                                  "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            return self.send(200, json.dumps(board_summary()).encode("utf-8"), "application/json")
        if path.startswith("/api/task/"):
            if DEMO:
                from demo import demo_board, demo_task
                tid = path[len("/api/task/"):]
                if not re.match(r"^T-\d+$", tid):
                    return self.deny(400, "bad task id")
                b = demo_board()
                if not any(t["id"] == tid for t in b["tasks"]):
                    return self.deny(404, "unknown task")
                return self.send(200, json.dumps(demo_task(tid)).encode("utf-8"), "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            tid = path[len("/api/task/"):]
            if not re.match(r"^T-\d+$", tid):
                return self.deny(400, "bad task id")
            detail = task_detail(tid)
            if detail is None:
                return self.deny(404, "unknown task")
            return self.send(200, json.dumps(detail).encode("utf-8"), "application/json")
        if path == "/api/file":
            if DEMO:
                from demo import demo_file
                relp = (qs.get("path", [""])[0] or "")
                if relp.endswith(".png"):
                    return self.send(200, b"\x89PNG\r\n\x1a\ndemo", "image/png")
                text = demo_file(relp)
                if not text:
                    text = f"# Demo file\n\nSimulated content for {relp}.\n"
                return self.send(200, text.encode("utf-8"), "text/markdown")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            relp = (qs.get("path", [""])[0] or "")
            target = resolve_office_file(relp) or resolve_notes_file(relp)
            if target is None:
                return self.deny(403, "forbidden")
            if not target.is_file():
                return self.deny(404, "not found")
            try:
                data = target.read_bytes()
            except OSError:
                return self.deny(404, "not found")
            suf = target.suffix.lower()
            if suf in (".log", ".patch", ".txt", ".md", ".json"):
                if len(data) > 512 * 1024:
                    tail = data[-512 * 1024:]
                    nl = tail.find(b"\n")
                    data = tail[nl + 1:] if nl >= 0 else tail
                ctype = "text/plain" if suf in (".log", ".patch", ".txt") else \
                    "application/json" if suf == ".json" else "text/markdown"
                return self.send(200, data, ctype)
            if suf == ".png":
                return self.send(200, data, "image/png")
            return self.deny(403, "forbidden")
        if path == "/api/tail":
            if DEMO:
                from demo import demo_tail
                relp = (qs.get("path", [""])[0] or "")
                off_raw = (qs.get("offset", ["0"])[0] or "0")
                try:
                    offset = int(off_raw)
                    if offset < 0:
                        raise ValueError()
                except ValueError:
                    return self.deny(400, "bad offset")
                return self.send(200, json.dumps(demo_tail(relp, offset)).encode("utf-8"),
                                  "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            relp = (qs.get("path", [""])[0] or "")
            target = resolve_office_file(relp)
            if target is None:
                return self.deny(403, "forbidden")
            if not target.is_file():
                return self.deny(404, "not found")
            off_raw = (qs.get("offset", ["0"])[0] or "0")
            try:
                offset = int(off_raw)
                if offset < 0:
                    raise ValueError()
            except ValueError:
                return self.deny(400, "bad offset")
            try:
                size = target.stat().st_size
            except OSError:
                return self.deny(404, "not found")
            if offset > size:
                offset = 0
            try:
                with target.open("rb") as f:
                    f.seek(offset)
                    chunk = f.read(64 * 1024)
            except OSError:
                return self.deny(404, "not found")
            if len(chunk) == 64 * 1024:
                try:
                    with target.open("rb") as f:
                        f.seek(offset + len(chunk))
                        extra = f.read(1)
                except OSError:
                    extra = b""
                if extra:
                    nl = chunk.rfind(b"\n")
                    if nl >= 0:
                        chunk = chunk[:nl + 1]
            text = chunk.decode("utf-8", errors="replace")
            done = target.name.endswith(".log") and not target.name.endswith(".live.log")
            return self.send(200, json.dumps({"text": text, "offset": offset + len(chunk),
                                                      "size": size, "done": done}).encode("utf-8"),
                              "application/json")
        if path == "/api/screenshots":
            if DEMO:
                return self.send(200, json.dumps([]).encode("utf-8"), "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            return self.send(200, json.dumps(screenshots_list()).encode("utf-8"), "application/json")
        if path == "/api/commands":
            if DEMO:
                return self.send(200, json.dumps(
                    {"pending": [{"id": "demo1", "action": "set_priority", "task": "T-2"}],
                     "done": [{"id": "demo0", "action": "set_priority", "task": "T-1", "result": "applied"}]}).encode("utf-8"),
                                  "application/json")
            if not self.check_manage():
                return
            cmd_dir = ROOT / "project" / "commands"
            done_dir = cmd_dir / "done"
            pending = []
            try:
                files = sorted((p for p in cmd_dir.glob("*.json") if p.is_file()), key=lambda p: p.name)
            except OSError:
                files = []
            for p in files:
                try:
                    pending.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:  # noqa: BLE001
                    pending.append({"id": p.stem, "action": "?", "malformed": True})
            done = []
            try:
                dfiles = sorted((p for p in done_dir.glob("*.json") if p.is_file()),
                                key=lambda p: p.name, reverse=True)[:20] if done_dir.is_dir() else []
            except OSError:
                dfiles = []
            for p in dfiles:
                try:
                    done.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:  # noqa: BLE001
                    continue
            return self.send(200, json.dumps({"pending": pending, "done": done}).encode("utf-8"),
                              "application/json")
        if path == "/api/stats":
            if DEMO:
                from demo import demo_stats
                hours_raw = (qs.get("hours", ["24"])[0] or "24")
                try:
                    hours = int(hours_raw)
                except ValueError:
                    return self.deny(400, "bad hours")
                if hours not in (6, 24, 72, 168):
                    return self.deny(400, "bad hours")
                return self.send(200, json.dumps(demo_stats(hours)).encode("utf-8"), "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            hours_raw = (qs.get("hours", ["24"])[0] or "24")
            try:
                hours = int(hours_raw)
            except ValueError:
                return self.deny(400, "bad hours")
            if hours not in (6, 24, 72, 168):
                return self.deny(400, "bad hours")
            try:
                return self.send(200, json.dumps(cached_stats(hours)).encode("utf-8"), "application/json")
            except Exception as e:  # noqa: BLE001
                return self.deny(500, f"stats failed: {e}"[:200])
        if path == "/api/notes":
            if DEMO:
                from demo import demo_notes
                return self.send(200, json.dumps(demo_notes()).encode("utf-8"), "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            st = _stats_mod()
            try:
                data = st.build_notes(ROOT) if st else {"plans": [], "docs": []}
            except Exception:  # noqa: BLE001
                data = {"plans": [], "docs": []}
            return self.send(200, json.dumps(data).encode("utf-8"), "application/json")
        if path == "/api/build":
            if DEMO:
                from demo import demo_build
                return self.send(200, json.dumps(demo_build()).encode("utf-8"), "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            return self.send(200, json.dumps(build_info()).encode("utf-8"), "application/json")
        if path == "/api/approvals":
            if DEMO:
                from demo import demo_approvals
                return self.send(200, json.dumps(demo_approvals()).encode("utf-8"),
                                  "application/json")
            if MANAGE and not host_allowed(self.headers.get("Host", "")):
                return self.deny(403, "bad host")
            return self.send(200, json.dumps({"pending": list_approvals()}).encode("utf-8"),
                              "application/json")
        if path == "/api/config":
            if DEMO:
                from demo import demo_config
                return self.send(200, json.dumps(demo_config()).encode("utf-8"),
                                  "application/json")
            if not self.check_manage():
                return
            cfg = read_config()
            if cfg is None:
                return self.deny(500, "cannot read config")
            agents = cfg.get("agents") or {}
            return self.send(200, json.dumps({
                "config": cfg, "mtime": config_mtime(), "models": models_list(),
                "paid": {n: agent_paid(cfg, n) for n in agents},
                "kinds": {n: agent_kind(cfg, n) for n in agents},
            }).encode("utf-8"), "application/json")
        if path in ("/api/requests", "/api/probe"):
            if DEMO:
                if path == "/api/requests":
                    stub = {"open": ["Demo: add a fishing rod"], "handled": ["Demo: menu polish (T-1)"]}
                else:
                    stub = {"running": False, "results": {"coder_1": {"state": "ok", "seconds": 1.2, "detail": "OK"}}}
                return self.send(200, json.dumps(stub).encode("utf-8"), "application/json")
            if not self.check_manage():
                return
            if path == "/api/requests":
                return self.send(200, json.dumps(parse_requests(read(ROOT / "project" / "OWNER_REQUESTS.md"))).encode("utf-8"),
                                 "application/json")
            with _probe_lock:
                snap = {"running": _probe["running"], "results": dict(_probe["results"])}
            return self.send(200, json.dumps(snap).encode("utf-8"), "application/json")
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (HERE / rel).resolve()
        if HERE not in f.parents or not f.is_file() or f.suffix not in {".html", ".css", ".js", ".png", ".woff2", ".txt"}:
            return self.send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if f.suffix == ".woff2":
            ctype = "font/woff2"
        self.send(200, f.read_bytes(), ctype)

    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlsplit(self.path).path)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length < 0:
            return self.deny(400, "bad length")
        if length > MAX_BODY:
            return self.deny(413, "body too large")
        if DEMO and path.startswith("/api/"):
            return self.deny(409, "demo mode")
        if not self.check_manage():
            return
        try:
            data = json.loads(self.rfile.read(length) if length else b"{}")
        except ValueError:
            return self.deny(400, "bad json")
        if not isinstance(data, dict):
            return self.deny(400, "bad json")
        if path == "/api/control":
            return self.handle_control(data)
        if path == "/api/requests":
            return self.handle_request_post(data)
        if path == "/api/probe":
            return self.handle_probe_post()
        if path == "/api/notify-test":
            return self.handle_notify_post()
        if path == "/api/command":
            return self.handle_command_post(data)
        if path == "/api/config":
            return self.handle_config_post(data)
        if path == "/api/approval":
            return self.handle_approval_post(data)
        return self.deny(404, "unknown endpoint")

    def handle_config_post(self, data: dict) -> None:
        base = data.get("base_mtime")
        changes = data.get("changes")
        if not isinstance(base, (int, float)) or not isinstance(changes, dict):
            return self.deny(400, "base_mtime and changes required")
        with _write_lock:
            try:
                raw_before = config_path().read_text(encoding="utf-8")
            except OSError:
                return self.deny(500, "cannot read config")
            try:
                cur_mtime = config_path().stat().st_mtime
            except OSError:
                return self.deny(500, "cannot read config")
            if abs(cur_mtime - float(base)) > 0.01:
                return self.deny(409, "config changed since base_mtime")
            try:
                cfg = json.loads(raw_before)
            except ValueError:
                return self.deny(500, "cannot read config")
            try:
                new_cfg, summary, restart_needed = apply_config_changes(cfg, changes)
            except ConfigError as e:
                return self.deny(e.code, e.msg)
            mtime = write_config_file(new_cfg, raw_before)
        office_event(f"OFFICE config changed: {summary}"[:220])
        invalidate()
        self.send(200, json.dumps({"ok": True, "restart_needed": restart_needed,
                                   "mtime": mtime}).encode("utf-8"), "application/json")

    def handle_approval_post(self, data: dict) -> None:
        task = data.get("task", "")
        decision = data.get("decision", "")
        feedback = data.get("feedback", "")
        if not isinstance(task, str) or not TASK_ID_RE.match(task):
            return self.deny(400, "bad task")
        if decision not in ("approve", "revise"):
            return self.deny(400, "bad decision")
        if decision == "revise" and not (isinstance(feedback, str) and feedback.strip()):
            return self.deny(400, "feedback required for revise")
        req_path = approvals_dir() / f"{task}.json"
        if not req_path.is_file():
            return self.deny(409, "no request pending")
        dec_path = approvals_dir() / f"{task}.decision.json"
        payload = {"decision": decision, "feedback": feedback if isinstance(feedback, str) else "",
                   "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        with _write_lock:
            if not req_path.is_file():
                return self.deny(409, "no request pending")
            atomic_write(dec_path, json.dumps(payload, indent=2))
        invalidate()
        self.send(200, json.dumps({"ok": True}).encode("utf-8"), "application/json")

    def handle_command_post(self, data: dict) -> None:
        board = read_json(ROOT / "project" / "board.json") or {}
        code, err = validate_command(data, board)
        if code:
            return self.deny(code, err)
        cmd_dir = ROOT / "project" / "commands"
        try:
            cmd_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return self.deny(500, "cannot write commands") if hasattr(self, "deny") else None
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        cid = f"{stamp}-{secrets.token_hex(3)}"
        payload = {"id": cid, "at": dt.datetime.now().isoformat(timespec="seconds"),
                   "source": "office", **data}
        # id in the body (if any) must not override the generated one
        payload["id"] = cid
        text = json.dumps(payload, indent=2)
        try:
            with _write_lock:
                tmp = cmd_dir / (cid + ".json.tmp")
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, cmd_dir / (cid + ".json"))
        except OSError:
            return self.deny(500, "cannot write commands")
        invalidate()
        self.send(200, json.dumps({"ok": True, "id": cid}).encode("utf-8"), "application/json")

    def handle_control(self, data: dict) -> None:
        action = data.get("action", "")
        if action in ("plan_now", "restart", "stop"):
            name = {"plan_now": "PLAN_NOW", "restart": "RESTART", "stop": "STOP"}[action]
            atomic_write(ROOT / "project" / name,
                         f"requested from the Office at {dt.datetime.now().isoformat(timespec='seconds')}\n")
            office_event(f"OFFICE {action} requested")
        elif action == "cancel":
            if data.get("flag", "") not in ("STOP", "RESTART", "PLAN_NOW"):
                return self.deny(400, "unknown flag")
            try:
                (ROOT / "project" / data["flag"]).unlink()
            except OSError:
                pass
        elif action == "start":
            if _procs.get("orchestrator") is True:
                return self.deny(409, "orchestrator already running")
            try:
                (ROOT / "project" / "STOP").unlink()
            except OSError:
                pass
            subprocess.Popen(["cmd", "/c", "start", "", "start.bat"], cwd=ROOT)
            if data.get("supervisor") and _procs.get("supervisor") is not True:
                subprocess.Popen(["cmd", "/c", "start", "", "supervise.bat"], cwd=ROOT)
        elif action == "start_supervisor":
            if _procs.get("supervisor") is not True:
                subprocess.Popen(["cmd", "/c", "start", "", "supervise.bat"], cwd=ROOT)
        elif action == "play":
            subprocess.Popen(["cmd", "/c", "start", "", "play.bat"], cwd=ROOT)
        else:
            return self.deny(400, "unknown action")
        invalidate()
        self.send(200, json.dumps({"ok": True, "flags": flags_now()}).encode("utf-8"), "application/json")

    def handle_request_post(self, data: dict) -> None:
        text = data.get("text", "")
        if not isinstance(text, str):
            return self.deny(400, "text must be a string")
        text = text.strip()
        if not text or len(text) > 2000:
            return self.deny(400, "text must be 1-2000 chars")
        line = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"- {line} _(from the Office, {stamp})_"
        p = ROOT / "project" / "OWNER_REQUESTS.md"
        with _write_lock:
            atomic_write(p, insert_request(read(p), entry))  # re-read right before writing
        office_event("OFFICE request added")
        if data.get("plan_now") is True:
            atomic_write(ROOT / "project" / "PLAN_NOW",
                         f"requested from the Office at {dt.datetime.now().isoformat(timespec='seconds')}\n")
            office_event("OFFICE plan_now requested")
        invalidate()
        self.send(200, json.dumps({"ok": True}).encode("utf-8"), "application/json")

    def handle_probe_post(self) -> None:
        with _probe_lock:
            if _probe["running"]:
                return self.deny(409, "probe already running")
            agents = (read_json(ROOT / "orchestrator" / "config.json") or {}).get("agents") or {}
            _probe["results"] = {n: {"state": "pending", "seconds": 0.0, "detail": ""} for n in agents}
            _probe["running"] = True
        threading.Thread(target=run_probe_all, args=(agents,), daemon=True).start()
        self.send(200, json.dumps({"ok": True}).encode("utf-8"), "application/json")

    def handle_notify_post(self) -> None:
        cfg = read_json(ROOT / "orchestrator" / "config.json") or {}
        topic = (cfg.get("notify") or {}).get("ntfy_topic")
        if not topic:
            return self.deny(409, "no ntfy_topic in config")
        board = read_json(ROOT / "project" / "board.json") or {}
        game = board.get("project") or ROOT.name
        title = f"{game}: test from the Office".encode("ascii", "replace").decode()
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=b"Test notification from the Office",
                                     method="POST",
                                     headers={"Title": title, "Priority": "default", "Tags": "skull"})
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as e:  # noqa: BLE001
            return self.deny(502, f"notify failed: {e}"[:200])
        self.send(200, json.dumps({"ok": True}).encode("utf-8"), "application/json")


def main() -> int:
    global ROOT, DEMO, MANAGE, TOKEN, LAN_IP
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="game folder (default: the folder this office/ is in)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="also serve on your local network (for a phone)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--demo", action="store_true", help="preview simulated workers without running agents or reading a project")
    ap.add_argument("--manage", action="store_true", help="enable controls: plan/restart/stop/start, owner requests, health tools")
    ap.add_argument("--token", help="manage-mode token (default: a random one is generated)")
    a = ap.parse_args()
    if a.project:
        ROOT = Path(a.project).resolve()
    DEMO = a.demo
    MANAGE = a.manage
    if MANAGE:
        TOKEN = a.token or secrets.token_urlsafe(16)
    if not DEMO and not (ROOT / "project").is_dir():
        print(f"{ROOT} doesn't look like a game project (no project/ folder). Use --project.")
        return 1
    if not DEMO:
        threading.Thread(target=watch_processes, daemon=True).start()
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    if a.lan:
        try:
            LAN_IP = socket.gethostbyname(socket.gethostname())
        except OSError:
            pass
    server = None
    for port in range(a.port, a.port + 20):
        try:
            server = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            continue
    if not server:
        print("No free port found.")
        return 1
    q = f"?token={TOKEN}" if MANAGE else ""
    url = f"http://localhost:{server.server_port}/{q}"
    print(f"The Office {'demo' if DEMO else 'for ' + ROOT.name} is open at {url}")
    if a.lan:
        if LAN_IP:
            print(f"On your phone (same Wi-Fi): http://{LAN_IP}:{server.server_port}/{q}  (allow Python through the firewall)")
    if MANAGE:
        print("Manage mode is ON: the page can plan, restart, stop and start the team. Keep the token URL private.")
    print("Close this window to close the office. The team keeps working either way.")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
