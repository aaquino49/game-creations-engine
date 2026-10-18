"""Simulated office activity for previews. Never reads or writes project files."""
import datetime as dt
import time

STARTED = time.monotonic()
SCENES = ("working", "checks", "idle", "limits", "complete", "closed")


def demo_state(scene="auto"):
    tick = int((time.monotonic() - STARTED) / 12)
    scene = scene if scene in SCENES else SCENES[tick % len(SCENES)]
    clock = dt.datetime.now()
    until = (clock + dt.timedelta(minutes=24)).strftime("%H:%M")
    agents = [{"id": a_id, "label": label, "tool": tool, "model": model, "account": account,
               "paid": a_id == "coder_1", "coder": a_id == "coder_1"}
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
            "planner": {"busy": scene in ("working", "checks")}, "supervisor_msg": "Demo patrol",
            "milestones": [{"id": "M1", "title": "Open the studio", "done": 12, "total": 12, "active": 0, "blocked": 0},
                           {"id": "M2", "title": "Bring the office to life", "done": 18 if scene == "complete" else 11,
                            "total": 18, "active": len(jobs), "blocked": 0}],
            "events": events, "complete": scene == "complete", "configured": True, "demo": True,
            "scene": scene, "counts": {"done": 30 if scene == "complete" else 23, "in_progress": sum(l["state"] == "busy" for l in lanes),
                                      "ready": 0 if scene == "complete" else 4, "backlog": 0, "blocked": 0}}
