"""Simulated office activity for previews. Never reads or writes project files."""
import datetime as dt
import random
import time

STARTED = time.monotonic()
SCENES = ("working", "checks", "idle", "limits", "complete", "closed")

_DEMO_TASKS = None
_DEMO_TAIL = {"lines": [], "n": 0}


def _rng(seed=20261018):
    return random.Random(seed)


def demo_state(scene="auto"):
    tick = int((time.monotonic() - STARTED) / 12)
    scene = scene if scene in SCENES else SCENES[tick % len(SCENES)]
    clock = dt.datetime.now()
    until = (clock + dt.timedelta(minutes=24)).strftime("%H:%M")
    agents = [{"id": a_id, "label": label, "tool": tool, "model": model, "account": account,
               "paid": a_id == "coder_1", "coder": a_id.startswith("coder_")}
              for a_id, label, tool, model, account in (
        ("quarterback", "Quarterback", "claude", "claude-opus-5-5", "anthropic"),
        ("qa_lead", "QA lead", "codex", "gpt-6.1-sol", "openai"),
        ("coder_1", "Coder 1 (paid)", "opencode", "meta/muse-spark-1.3-contributor", "meta_api"),
        ("coder_2", "Coder 2", "codex", "gpt-6-luna", "openai"),
        ("coder_3", "Coder 3", "opencode", "opencode/beam-free", "coder_3"),
        ("coder_4", "Coder 4", "opencode", "opencode/longcat-2.5-preview-free", "coder_4"),
        ("coder_5", "Coder 5", "opencode", "opencode/deepseek-v4.1-flash-free", "coder_5"))]
    lanes = [{"lane": name, "state": "idle", "activity": ""} for name in "ABC"]
    jobs = []
    if scene in ("working", "checks"):
        for lane, agent, step, task, title in (
            ("A", "coder_1", "work", "T-042", "Make the little workers come alive"),
            ("B", "qa_lead", "qa", "T-043", "Check the office at every screen size"),
            ("C", "quarterback", "review", "T-044", "Polish the coffee-break conversations")):
            if scene == "checks":
                step = {"A": "checks", "B": "merge", "C": "work"}[lane]
            lanes[ord(lane) - ord("A")] = {"lane": lane, "state": "busy", "task": task,
                "title": title, "step": step, "agent": agent, "type": "code", "activity": step}
            if step in ("work", "qa", "review"):
                jobs.append({"agent": agent, "station": "lane:" + lane, "step": step,
                             "task": task, "title": title, "type": "code"})
        jobs.append({"agent": "quarterback", "station": "plan", "step": "plan", "task": "",
                     "title": "A cozy lounge and a very good office dog"})
    for a in agents:
        if a["id"] == "coder_3":
            a["benched"] = True
        else:
            a["benched"] = False
    if scene in ("working", "limits"):
        for a in agents:
            if a["id"] in ("coder_2", "coder_4"):
                a["limit"] = {"state": "limited" if a["id"] == "coder_2" else "down", "until": until}
            elif a["id"] == "coder_5":
                a["limit"] = {"state": "gone", "until": until}
        if scene == "limits":
            agents[1]["limit"] = {"state": "limited", "until": until}
    accounts = []
    seen = {}
    for a in agents:
        seen.setdefault(a["account"], []).append(a["id"])
    labels = {"anthropic": "Anthropic subscription", "openai": "OpenAI subscription",
              "meta_api": "Meta API (pay-per-use)"}
    for acct, members in seen.items():
        hits = [(m, next(x for x in agents if x["id"] == m)["limit"]) for m in members
                if "limit" in next(x for x in agents if x["id"] == m)]
        if hits:
            m, lim = max(hits, key=lambda h: ({"gone": 3, "down": 2, "limited": 1}[h[1]["state"]], h[1]["until"]))
            accounts.append({"id": acct, "label": labels.get(acct, acct),
                             "state": lim["state"], "until": lim["until"], "agents": members})
        else:
            accounts.append({"id": acct, "label": labels.get(acct, acct), "state": "ok", "agents": members})
    accounts.sort(key=lambda x: ({"gone": 3, "down": 2, "limited": 1}.get(x.get("state"), 0), x["id"]), reverse=True)
    events = [{"id": tick * 10, "t": clock.strftime("%H:%M"), "kind": "boot", "text": "ORCHESTRATOR START (demo)"},
              {"id": tick * 10 + 1, "t": clock.strftime("%H:%M"), "kind": "done", "task": "T-041", "lane": "A", "text": "DONE T-041"},
              {"id": tick * 10 + 2, "t": clock.strftime("%H:%M"), "kind": "supervisor", "text": "SUPERVISOR: all lanes healthy"}]
    if scene == "complete":
        events.append({"id": tick * 10 + 3, "t": clock.strftime("%H:%M"), "kind": "complete", "text": "PROJECT COMPLETE"})
    return {"game": "Tiny Team Studio", "time": clock.strftime("%H:%M"), "updated": clock.strftime("%H:%M"),
            "orchestrator": scene != "closed", "supervisor": scene != "closed", "flags": [],
            "now": "Simulated activity", "lanes": lanes, "jobs": jobs, "agents": agents,
            "accounts": accounts,
            "approvals": demo_approvals()["pending"],
            "approval_wait": [r["task"] for r in demo_approvals()["pending"]],
            "planner": {"busy": scene in ("working", "checks")}, "supervisor_msg": "Demo patrol",
            "milestones": [{"id": "M1", "title": "Open the studio", "done": 12, "total": 12, "active": 0, "blocked": 0},
                           {"id": "M2", "title": "Bring the office to life", "done": 18 if scene == "complete" else 11,
                            "total": 18, "active": len(jobs), "blocked": 0}],
            "events": events, "complete": scene == "complete", "configured": True, "demo": True,
            "scene": scene, "counts": {"done": 30 if scene == "complete" else 23, "in_progress": sum(l["state"] == "busy" for l in lanes),
                                      "ready": 0 if scene == "complete" else 4, "backlog": 0, "blocked": 0}}


# ------------------------------------------------------------------ phase 3 demo (deterministic, seeded)

_TITLES = ["Menu polish", "Save slots", "Footstep sounds", "Boss arena", "Tutorial signs",
           "Night lighting", "Controller help", "Pause menu", "Coin magnet", "Slime sprites",
           "Quest log", "Map fog", "Dialogue box", "Hit sparks", "Shop prices",
           "Checkpoint flag", "Swim physics", "Photo mode", "Credits roll", "Daily seed",
           "Cloud saves", "Emoji chat", "Fishing rod", "Pet corgi", "Snow storm",
           "Lantern glow", "Minimap pins", "Boss music", "Idle anims", "Patch notes"]


def demo_board():
    """About 30 tasks over 3 milestones with dependencies and all statuses."""
    global _DEMO_TASKS
    if _DEMO_TASKS is not None:
        return _DEMO_TASKS
    rng = _rng()
    statuses = (["done"] * 12 + ["in_progress"] * 3 + ["ready"] * 5 + ["backlog"] * 6
                + ["blocked"] * 2 + ["dropped"] * 2)
    rng.shuffle(statuses)
    tasks = []
    for i in range(30):
        n = i + 1
        tid = f"T-{n}"
        mid = "M1" if n <= 10 else "M2" if n <= 20 else "M3"
        deps = []
        if n > 1 and rng.random() < 0.5:
            deps = [f"T-{rng.randint(1, n - 1)}"]
        if n > 3 and rng.random() < 0.2:
            deps.append(f"T-{rng.randint(1, n - 1)}")
        deps = sorted(set(deps))
        tasks.append({"id": tid, "title": _TITLES[i], "status": statuses[i],
                      "milestone": mid, "priority": rng.randint(1, 5),
                      "type": rng.choice(["code", "code", "code", "asset", "design", "qa"]),
                      "owner": "coder", "depends_on": deps,
                      "attempts": rng.randint(1, 3) if statuses[i] in ("done", "blocked") else rng.randint(0, 2)})
    _DEMO_TASKS = {"tasks": tasks, "milestones": ["M1", "M2", "M3"]}
    return _DEMO_TASKS


def demo_task(tid):
    """Task details with 1-3 attempts, histories and review summaries."""
    b = demo_board()
    t = next((x for x in b["tasks"] if x["id"] == tid), None)
    if t is None:
        t = dict(b["tasks"][0])
        t = dict(t)
        t["id"] = tid
    rng = _rng(hash(tid) % (2 ** 31))
    n = max(1, min(3, t.get("attempts", 1) or 1))
    workers = ["coder_1", "coder_3", "coder_2", "qa_lead"]
    attempts, history = [], []
    for a in range(1, n + 1):
        w = workers[(hash(tid) + a) % len(workers)]
        verdict = "approve" if (a == n and t["status"] == "done") else rng.choice(["approve", "revise"])
        attempts.append({"n": a, "files": [
            {"name": "work.json", "size": 120, "kind": "json"},
            {"name": f"work.{w}.log", "size": 300, "kind": "log"}],
            "work": {"status": "done", "summary": f"demo work for {tid} attempt {a}", "worker": w},
            "qa": {"verdict": "pass", "summary": f"demo QA {a}"},
            "review": {"verdict": verdict, "summary": f"demo review {a}: {verdict}"}})
        history.append({"attempt": a, "at": "2026-10-17 10:00:00", "worker": w,
                        "work": "done", "checks": True, "qa": "pass",
                        "checks_after_qa": True, "review": verdict})
    out = dict(t)
    out["brief"] = f"# {t['id']}: {t['title']}\n\nDemo brief for {t['title']}.\n"
    out["attempts_count"] = n
    out["attempts"] = attempts
    out["history"] = history
    out["acceptance"] = ["demo criterion one", "demo criterion two"]
    out["description"] = f"Demo description for {t['title']}."
    return out


def demo_tail(path, offset):
    """A fake .log that grows by a few lines per call, so the Live tab animates."""
    try:
        off = int(offset)
        if off < 0:
            off = 0
    except (TypeError, ValueError):
        off = 0
    _DEMO_TAIL["n"] += 1
    for _ in range(3):
        _DEMO_TAIL["lines"].append(
            f"2026-10-18 12:{_DEMO_TAIL['n']:02d}:00  demo {_DEMO_TAIL['n']} working on {path or 'project/runs/T-1/a1/work.coder_1.log'}\n")
        _DEMO_TAIL["n"] += 0  # keep counter stable per call batch
    full = "".join(_DEMO_TAIL["lines"])
    if off > len(full):
        off = 0
    text = full[off:]
    return {"text": text, "offset": len(full), "size": len(full), "done": False}


def demo_file(path):
    if (path or "").endswith(".png"):
        return None  # caller serves bytes instead
    if "decisions" in (path or ""):
        return "# Decisions (demo)\n\n| Date | Decision | Why |\n|---|---|---|\n| 2026-10-17 | Demo ships | showcase |\n"
    return f"# Demo file\n\nThis is simulated content for {path}.\n"


def demo_stats(hours=24):
    """3 days of stats: scorecards, throughput, a Gantt with naps, fallbacks, incidents."""
    now = dt.datetime.now()
    rng = _rng(hours)
    agents = ["coder_1", "coder_2", "coder_3", "qa_lead", "quarterback"]
    scorecards = []
    for i, a in enumerate(agents):
        scorecards.append({"agent": a, "attempts": 8 - i, "first_pass": 3 - min(i, 2),
                           "approval_rate": round(0.75 - i * 0.05, 3),
                           "checks_rate": round(0.9 - i * 0.03, 3),
                           "qa_rate": round(0.8 - i * 0.04, 3),
                           "median_work_min": round(18.0 + i * 3.5, 1),
                           "blocked": 1 if a == "coder_3" else 0,
                           "substitutions": 2 if a == "coder_3" else 0})
    scorecards.sort(key=lambda d: (-d["first_pass"], -(d["approval_rate"] or 0)))
    bh = 1 if hours in (6, 24) else 6
    n = max(1, hours // bh)
    start = now - dt.timedelta(hours=hours)
    buckets = [{"start": (start + dt.timedelta(hours=i * bh)).strftime("%Y-%m-%d %H:%M:%S"),
                "count": (i * 7 + hours) % 4} for i in range(n)]
    series = [{"t": (start + dt.timedelta(hours=i * bh)).strftime("%Y-%m-%d %H:%M:%S"),
               "open": {"M1": max(0, 4 - i // 4), "M2": 8, "M3": 10}} for i in range(n + 1)]
    gantt_bars_a = []
    gantt_bars_b = []
    for i in range(5):
        s = now - dt.timedelta(hours=23 - i * 4)
        e = s + dt.timedelta(hours=3)
        gantt_bars_a.append({"task": f"T-{10 + i}", "title": _TITLES[i],
                             "start": s.strftime("%Y-%m-%d %H:%M:%S"),
                             "end": e.strftime("%Y-%m-%d %H:%M:%S"),
                             "outcome": "done", "attempts": 1, "duration_min": 180.0})
    for i in range(4):
        s = now - dt.timedelta(hours=21 - i * 5)
        e = s + dt.timedelta(hours=4)
        gantt_bars_b.append({"task": f"T-{15 + i}", "title": _TITLES[5 + i],
                             "start": s.strftime("%Y-%m-%d %H:%M:%S"),
                             "end": e.strftime("%Y-%m-%d %H:%M:%S"),
                             "outcome": "done" if i < 3 else "running",
                             "attempts": 2, "duration_min": 240.0})
    gantt_bars_b[-1]["end"] = now.strftime("%Y-%m-%d %H:%M:%S")
    gantt = {"lanes": [{"lane": "A", "bars": gantt_bars_a},
                       {"lane": "B", "bars": gantt_bars_b}],
             "naps": [{"account": "openai", "bars": [
                 {"start": (now - dt.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S"),
                  "end": (now - dt.timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),
                  "reason": "USAGE LIMIT", "hours": 3.0}]}],
             "now": now.strftime("%Y-%m-%d %H:%M:%S")}
    routing = {"flows": [{"from": "coder_2", "to": "coder_3", "count": 3},
                         {"from": "coder_1", "to": "coder_3", "count": 1}],
               "counts": {a: {"usage_limit": 1 if a == "coder_2" else 0, "preemptive": 0,
                              "provider_down": 0, "model_gone": 0, "quick_fail": 0,
                              "agent_fail": 0} for a in agents}}
    quota = {"accounts": [
        {"id": "openai", "state": "ok", "until": "", "limits": 2, "hours_limited": 5.0},
        {"id": "meta_api", "state": "ok", "until": "", "limits": 0, "hours_limited": 0.0}]}
    incidents = {"counts": {"supervisor_ai": 2},
                 "items": [
                     {"time": now.strftime("%Y-%m-%d %H:%M:%S"), "type": "supervisor_ai",
                      "agent": "claude", "reason": "lane B quiet", "outcome": "done",
                      "summary": "nudged lane B", "duration_min": 4.0},
                     {"time": (now - dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                      "type": "supervisor_ai", "agent": "codex", "reason": "stale lock",
                      "outcome": "in progress", "summary": "", "duration_min": None}]}
    opencode = {"days1": {"total": 0.16, "models": {
        "meta/muse-spark-1.3-contributor": {"messages": 282, "input_tokens": 674300,
                                            "output_tokens": 193400, "cost": 0.1622}}},
        "days7": {"total": 1.2, "models": {
            "meta/muse-spark-1.3-contributor": {"messages": 900, "input_tokens": 2100000,
                                               "output_tokens": 600000, "cost": 0.5},
            "opencode/beam-free": {"messages": 700, "input_tokens": 1500000,
                                   "output_tokens": 400000, "cost": 0.4},
            "opencode/deepseek-v4.1-flash-free": {"messages": 500, "input_tokens": 900000,
                                                 "output_tokens": 300000, "cost": 0.3}}},
        "error": None, "updated": time.time()}
    codex = {"primary": {"used_percent": 42.0, "window_minutes": 300, "resets_at": int(time.time()) + 3600},
             "secondary": {"used_percent": 11.0, "window_minutes": 10080, "resets_at": int(time.time()) + 86400}}
    return {"hours": hours, "now": now.strftime("%Y-%m-%d %H:%M:%S"),
            "window_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "scorecards": scorecards, "scorecards_all": scorecards,
            "throughput": {"bucket_hours": bh, "buckets": buckets},
            "burndown": {"milestones": ["M1", "M2", "M3"], "series": series},
            "eta": {"milestone": {"id": "M2", "remaining": 8, "label": "~4.0 h", "low": False},
                    "board": {"remaining": 18, "label": "~9.0 h", "low": False},
                    "done_12h": 24, "rate_per_hour": 2.0},
            "gantt": gantt, "routing": routing, "quota": quota,
            "codex": codex, "opencode": opencode, "paid_models": ["meta/muse-spark-1.3-contributor"],
            "incidents": incidents}


def demo_notes():
    now = dt.datetime.now()
    plans = [
        {"time": now.strftime("%Y-%m-%d %H:%M:%S"), "reason": "demo plan two",
         "duration_min": 6.0, "summary": "planned the showcase board"},
        {"time": (now - dt.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
         "reason": "demo plan one", "duration_min": 4.0, "summary": "seeded three milestones"}]
    docs = [{"name": "decisions", "path": "project/decisions.md", "mtime": now.strftime("%Y-%m-%d %H:%M:%S")},
            {"name": "assumptions", "path": "project/assumptions.md", "mtime": now.strftime("%Y-%m-%d %H:%M:%S")},
            {"name": "PM notes", "path": "project/PM_NOTES.md", "mtime": now.strftime("%Y-%m-%d %H:%M:%S")},
            {"name": "milestone M1", "path": "project/milestones/M1.md", "mtime": now.strftime("%Y-%m-%d %H:%M:%S")}]
    return {"plans": plans, "docs": docs}


def demo_build():
    now = dt.datetime.now()
    return {"exe": "builds/demo-game.exe", "exists": True,
            "mtime": now.strftime("%Y-%m-%d %H:%M"), "size_mb": 42.5, "tag": "v1.0-demo"}


# ------------------------------------------------------------------ phase 4 demo (settings + approvals)

def demo_config():
    """Settings view demo: roster, fallbacks, lanes, approval gate and spend cap."""
    cfg = {
        "agents": {
            "quarterback": {"cmd": ["claude", "-p", "{prompt}", "--model", "claude-opus-5-5",
                                    "--dangerously-skip-permissions"],
                            "kind": "claude", "model": "claude-opus-5-5",
                            "account": "anthropic", "label": "Quarterback"},
            "qa_lead": {"cmd": ["codex", "exec", "-m", "gpt-6.1-sol",
                                "--dangerously-bypass-approvals-and-sandbox",
                                "--skip-git-repo-check", "{prompt}", "{images}"],
                        "kind": "codex", "model": "gpt-6.1-sol",
                        "account": "openai", "label": "QA lead"},
            "coder_1": {"cmd": ["opencode", "run", "--auto", "-m",
                                "meta/muse-spark-1.3-contributor", "{prompt}"],
                        "kind": "opencode", "model": "meta/muse-spark-1.3-contributor",
                        "account": "meta_api", "label": "Coder 1 (paid)"},
            "coder_2": {"cmd": ["codex", "exec", "-m", "gpt-6-luna",
                                "--dangerously-bypass-approvals-and-sandbox",
                                "--skip-git-repo-check", "{prompt}", "{images}"],
                        "kind": "codex", "model": "gpt-6-luna",
                        "account": "openai", "label": "Coder 2"},
            "coder_3": {"cmd": ["opencode", "run", "--auto", "-m",
                                "opencode/beam-free", "{prompt}"],
                        "kind": "opencode", "model": "opencode/beam-free",
                        "account": "coder_3", "label": "Coder 3"},
            "coder_4": {"cmd": ["opencode", "run", "--auto", "-m",
                                "opencode/longcat-2.5-preview-free", "{prompt}"],
                        "kind": "opencode", "model": "opencode/longcat-2.5-preview-free",
                        "account": "coder_4", "label": "Coder 4"},
            "coder_5": {"cmd": ["opencode", "run", "--auto", "-m",
                                "opencode/deepseek-v4.1-flash-free", "{prompt}"],
                        "kind": "opencode", "model": "opencode/deepseek-v4.1-flash-free",
                        "account": "coder_5", "label": "Coder 5"},
        },
        "coders": ["coder_1", "coder_2", "coder_3", "coder_4", "coder_5"],
        "paid_agents": ["coder_1"],
        "roles": {"quarterback": "quarterback", "qa": "qa_lead"},
        "fallback": {"coder_1:*": ["coder_2", "coder_3", "coder_4", "coder_5"],
                     "coder_2:*": ["coder_3", "coder_4", "coder_5", "coder_1"],
                     "coder_3:*": ["coder_2", "coder_4", "coder_5", "coder_1"],
                     "coder_4:*": ["coder_2", "coder_3", "coder_5", "coder_1"],
                     "coder_5:*": ["coder_2", "coder_3", "coder_4", "coder_1"]},
        "disabled_agents": ["coder_3"],
        "lanes": [{"name": "B", "dir": "C:/demo/gh_laneB"},
                  {"name": "C", "dir": "C:/demo/gh_laneC"}],
        "approval_gate": {"enabled": True, "types": ["code"], "workers": [],
                          "timeout_minutes": 60},
        "spend_cap": {"daily_usd": 5.0, "agents": ["coder_1"]},
        "_notes": "Demo config (never written).",
    }
    agents = cfg["agents"]
    return {"config": cfg, "mtime": 1729000000.0,
            "models": ["meta/muse-spark-1.3-contributor", "opencode/beam-free",
                       "opencode/longcat-2.5-preview-free",
                       "opencode/deepseek-v4.1-flash-free",
                       "gpt-6.1-sol", "gpt-6-luna", "claude-opus-5-5"],
            "paid": {n: (n in cfg["paid_agents"]) for n in agents},
            "kinds": {n: agents[n]["kind"] for n in agents}}


def demo_approvals():
    """One pending approval for the Approvals modal demo."""
    now = dt.datetime.now()
    return {"pending": [{
        "task": "T-042", "title": "Make the little workers come alive",
        "attempt": 1, "lane": "A", "worker": "coder_1",
        "requested_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": "Demo work summary.",
        "review_summary": "Demo review: approve.",
        "qa_verdict": "pass", "checks_summary": "12 passed",
        "patch": "project/runs/T-042/a1/approval.patch",
        "screenshot": "project/runs/T-042/a1/screenshot_shot1.png",
    }]}
