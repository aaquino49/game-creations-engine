"""Office Phase 3 stats: pure functions over project/events.log + project/board.json.

Stdlib only, no HTTP. All parsers are defensive: unknown or malformed lines
are skipped and never raise.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

TIME_FMT = "%Y-%m-%d %H:%M:%S"
EVENT_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+(.*)$")
ALLOWED_HOURS = (6, 24, 72, 168)


def parse_time(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, TIME_FMT)
    except (ValueError, TypeError):
        return None


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _events(root: Path) -> list[tuple[dt.datetime, str]]:
    """Whole events.log as (time, text), skipping malformed lines."""
    out: list[tuple[dt.datetime, str]] = []
    for line in _read_text(root / "project" / "events.log").splitlines():
        try:
            m = EVENT_RE.match(line)
            if not m:
                continue
            t = parse_time(m.group(1))
            if not t:
                continue
            out.append((t, m.group(2)))
        except Exception:
            continue
    return out


def _board(root: Path) -> dict:
    b = _read_json(root / "project" / "board.json")
    return b if isinstance(b, dict) else {}


def _config(root: Path) -> dict:
    c = _read_json(root / "orchestrator" / "config.json")
    return c if isinstance(c, dict) else {}


def _agents(root: Path) -> dict:
    cfg = _config(root)
    agents = cfg.get("agents") or {}
    return agents if isinstance(agents, dict) else {}


def _paid_models(root: Path) -> set:
    cfg = _config(root)
    paid = cfg.get("paid_agents", cfg.get("paid", [])) or []
    agents = _agents(root)
    out = set()
    for name in paid:
        a = agents.get(name) or {}
        model = a.get("model")
        if model:
            out.add(model)
    return out


# ------------------------------------------------------------------ opencode spend parser

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_BOX_RE = re.compile(r"[│┃║─━┌┐└┘├┤┬┴┼╭╮╯╰]")


def _num_tokens(s: str) -> int | None:
    s = (s or "").strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([KkMm])?$", s)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    suf = (m.group(2) or "").upper()
    if suf == "K":
        v *= 1000
    elif suf == "M":
        v *= 1000000
    return int(round(v))


def _money(s: str) -> float | None:
    m = re.search(r"\$\s*([\d,]+\.\d+|[\d,]+)", s or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_opencode_stats(text) -> dict:
    """Parse `opencode stats --models` box-drawing output.

    NOTE: this copy is kept identical to template/orchestrator/orchestrator.py:parse_opencode_stats
    (the orchestrator must stay a single file).
    Returns {"total": float|None, "models": {name: {messages, input_tokens,
    output_tokens, cost}}}. Garbage input gives {"total": None, "models": {}}.
    """
    try:
        if not isinstance(text, str) or not text:
            return {"total": None, "models": {}}
        clean = _ANSI_RE.sub("", text)
        clean = _BOX_RE.sub(" ", clean)
        lines = [ln.strip() for ln in clean.splitlines()]
        lines = [ln for ln in lines if ln]
        total = None
        for ln in lines:
            if "total cost" in ln.lower():
                total = _money(ln)
                break
        models: dict = {}
        cur: str | None = None
        buf: dict = {}
        keywords = ("messages", "input tokens", "output tokens", "cost")

        def flush():
            if cur and buf:
                models[cur] = dict(buf)

        for ln in lines:
            low = ln.lower()
            if "total cost" in low:
                continue
            if any(k in low for k in keywords):
                if cur is None:
                    continue
                if "messages" in low:
                    m = re.search(r"(\d[\d,]*)\s*$", ln)
                    if m:
                        try:
                            buf["messages"] = int(m.group(1).replace(",", ""))
                        except ValueError:
                            pass
                elif "input tokens" in low:
                    m = re.search(r"([\d.,]+\s*[KkMm]?)\s*$", ln)
                    if m:
                        v = _num_tokens(m.group(1))
                        if v is not None:
                            buf["input_tokens"] = v
                elif "output tokens" in low:
                    m = re.search(r"([\d.,]+\s*[KkMm]?)\s*$", ln)
                    if m:
                        v = _num_tokens(m.group(1))
                        if v is not None:
                            buf["output_tokens"] = v
                elif "cost" in low:
                    v = _money(ln)
                    if v is not None:
                        buf["cost"] = v
                continue
            # possible model header: single token with a slash, no spaces
            stripped = ln.strip()
            if "/" in stripped and " " not in stripped and len(stripped) < 120:
                if re.match(r"^[\w.\-/:@+]+$", stripped):
                    flush()
                    cur = stripped
                    buf = {}
                    continue
        flush()
        # drop empty model entries
        models = {k: v for k, v in models.items() if v}
        return {"total": total, "models": models}
    except Exception:
        return {"total": None, "models": {}}


# ------------------------------------------------------------------ codex usage (ported from orchestrator)

def codex_usage() -> dict | None:
    """Latest OpenAI rate-limit snapshot from the Codex CLI session logs."""
    try:
        base = Path.home() / ".codex" / "sessions"
        days = [dt.date.today() - dt.timedelta(days=i) for i in (0, 1)]
        recent = []
        for d in days:
            try:
                recent.extend((base / f"{d:%Y}" / f"{d:%m}" / f"{d:%d}").glob("rollout-*.jsonl"))
            except OSError:
                continue
        files = sorted((f for f in recent if f.is_file()),
                       key=lambda f: f.stat().st_mtime, reverse=True)[:3]
    except OSError:
        return None
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            stack = [obj]
            while stack:
                cur = stack.pop()
                try:
                    if isinstance(cur, dict):
                        rl = cur.get("rate_limits")
                        if isinstance(rl, dict) and "primary" in rl:
                            return rl
                        stack.extend(cur.values())
                    elif isinstance(cur, list):
                        stack.extend(cur)
                except Exception:
                    continue
    return None


# ------------------------------------------------------------------ scorecards (S1)

def _history_rates(hist: list) -> tuple[int, int, int, int, int, int]:
    """(n, first_approval_count_unused, approve, review_n, checks_pass, checks_n, ...) helper."""
    raise NotImplementedError


def _is_approve(v) -> bool:
    return isinstance(v, str) and v.strip().lower() == "approve"


def _is_pass_qa(v) -> bool:
    return isinstance(v, str) and v.strip().lower() == "pass"


def _is_checks_pass(v) -> bool:
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in ("pass", "true", "ok"):
        return True
    return False


def _has_review(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str) and v.strip() in ("", "?"):
        return False
    return True


def _scorecards_for(hist_entries: list[tuple[dict, dict]], agents: dict,
                    fallbacks: list[tuple[str, str]], blocked_workers: dict) -> list[dict]:
    """hist_entries: [((task, history_entry), parsed_at)]. fallbacks: [(limited, sub)]."""
    from statistics import median as _median
    per: dict[str, dict] = {}

    def row(a: str) -> dict:
        return per.setdefault(a, {"attempts": 0, "first_pass": 0, "approve": 0,
                                  "review_n": 0, "checks_pass": 0, "checks_n": 0,
                                  "qa_pass": 0, "qa_n": 0, "work_mins": [],
                                  "blocked": 0, "subs": 0})

    for (task, h) in hist_entries:
        w = h.get("worker")
        if not isinstance(w, str) or not w:
            continue
        r = row(w)
        r["attempts"] += 1
        if _has_review(h.get("review")):
            r["review_n"] += 1
            if _is_approve(h.get("review")):
                r["approve"] += 1
                if h.get("attempt") == 1:
                    r["first_pass"] += 1
        if h.get("checks") is not None and not (isinstance(h.get("checks"), str) and h.get("checks").strip() in ("", "?")):
            # checks field present (bool or str)
            if isinstance(h.get("checks"), bool) or isinstance(h.get("checks"), str):
                r["checks_n"] += 1
                if _is_checks_pass(h.get("checks")):
                    r["checks_pass"] += 1
        if h.get("qa") is not None and not (isinstance(h.get("qa"), str) and h.get("qa").strip() in ("", "?")):
            if isinstance(h.get("qa"), str):
                r["qa_n"] += 1
                if _is_pass_qa(h.get("qa")):
                    r["qa_pass"] += 1
        # work minutes attached later via h["_work_min"]
        if h.get("_work_min") is not None:
            try:
                r["work_mins"].append(float(h["_work_min"]))
            except (TypeError, ValueError):
                pass
    for limited, sub in fallbacks:
        if isinstance(sub, str) and sub:
            row(sub)["subs"] += 1
    for task_id, workers in blocked_workers.items():
        for w in workers:
            if w in per:
                per[w]["blocked"] += 1
    # ensure every configured agent has a row
    for a in agents:
        row(a)
    out = []
    for agent, r in per.items():
        med = None
        if r["work_mins"]:
            try:
                med = round(float(_median(sorted(r["work_mins"]))), 1)
            except Exception:
                med = None
        appr = round(r["approve"] / r["review_n"], 3) if r["review_n"] else None
        chk = round(r["checks_pass"] / r["checks_n"], 3) if r["checks_n"] else None
        qa = round(r["qa_pass"] / r["qa_n"], 3) if r["qa_n"] else None
        out.append({"agent": agent, "attempts": r["attempts"],
                    "first_pass": r["first_pass"], "approval_rate": appr,
                    "checks_rate": chk, "qa_rate": qa,
                    "median_work_min": med, "blocked": r["blocked"],
                    "substitutions": r["subs"]})
    out.sort(key=lambda d: (-d["first_pass"],
                            -(d["approval_rate"] if d["approval_rate"] is not None else -1),
                            d["agent"]))
    return out


def _attach_work_minutes(board_tasks: list, events: list[tuple[dt.datetime, str]]) -> None:
    """Mutate history entries in board_tasks, adding _work_min where computable."""
    # index events per task in order
    per_task: dict[str, list[tuple[dt.datetime, str]]] = {}
    for t, text in events:
        try:
            m = re.match(r"(?:START|DONE|BLOCKED|RECOVER|LANE|NEW TASK).*?(T-\d+)", text)
            m2 = re.match(r"(T-\d+) a\d+ (WORK|CHECKS|QA|REVIEW)", text)
            tid = None
            if m2:
                tid = m2.group(1)
            elif m:
                tid = m.group(1)
            else:
                # FALLBACK etc have no task; skip for work timing
                continue
            per_task.setdefault(tid, []).append((t, text))
        except Exception:
            continue
    for task in board_tasks:
        tid = task.get("id")
        evs = per_task.get(tid, [])
        # map (attempt -> WORK time)
        work_times: dict[int, dt.datetime] = {}
        for t, text in evs:
            try:
                m = re.match(r"T-\d+ a(\d+) WORK", text)
                if m:
                    work_times[int(m.group(1))] = t
            except Exception:
                continue
        # START times
        starts: dict[int, dt.datetime] = {}
        for t, text in evs:
            try:
                if text.startswith("START "):
                    # START has no attempt; it is attempt 1 start (or current run start)
                    starts.setdefault(1, t)
            except Exception:
                continue
        hist = task.get("history") or []
        if not isinstance(hist, list):
            continue
        for h in hist:
            if not isinstance(h, dict):
                continue
            try:
                att = h.get("attempt")
                att = int(att) if isinstance(att, (int, float)) or (isinstance(att, str) and att.isdigit()) else None
            except Exception:
                att = None
            if att is None or att not in work_times:
                continue
            wt = work_times[att]
            start = None
            if att == 1:
                start = starts.get(1)
                if start is None:
                    # fallback: first event for task before WORK
                    for t, _text in evs:
                        if t < wt:
                            if start is None or t > start:
                                # use earliest? spec: task's START event; if none, use first event?
                                # use earliest event before WORK as start
                                pass
                    # find earliest event for task
                    cands = [t for t, _ in evs if t < wt]
                    start = min(cands) if cands else None
            else:
                cands = [t for t, _ in evs if t < wt]
                # previous event for same task: the latest before WORK
                start = max(cands) if cands else None
            if start is not None:
                try:
                    h["_work_min"] = round((wt - start).total_seconds() / 60, 1)
                except Exception:
                    pass


# ------------------------------------------------------------------ throughput + burndown + ETA (S2)

def _done_times(events: list[tuple[dt.datetime, str]]) -> list[dt.datetime]:
    out = []
    for t, text in events:
        try:
            if re.match(r"DONE T-\d+", text):
                out.append(t)
        except Exception:
            continue
    return sorted(out)


def _throughput(done: list[dt.datetime], start: dt.datetime, now: dt.datetime,
                hours: int) -> dict:
    bh = 1 if hours in (6, 24) else 6
    n = max(1, hours // bh)
    buckets = []
    for i in range(n):
        bs = start + dt.timedelta(hours=i * bh)
        be = bs + dt.timedelta(hours=bh)
        c = sum(1 for d in done if bs <= d < be or (i == n - 1 and d == now and be >= now))
        # include events exactly at bucket end in next bucket except last; simpler: bs <= d < be
        buckets.append({"start": bs.strftime(TIME_FMT), "count": c})
    # recount strictly (fix last-bucket edge): recompute with bs <= d < be, plus d==now in last
    return {"bucket_hours": bh, "buckets": buckets}


def _burndown(board_tasks: list, events: list[tuple[dt.datetime, str]],
              start: dt.datetime, now: dt.datetime, hours: int) -> dict:
    # creation + close maps
    created: dict[str, dt.datetime] = {}
    closed: dict[str, dt.datetime] = {}
    first_seen: dict[str, dt.datetime] = {}
    for t, text in events:
        try:
            m = re.match(r"NEW TASK (T-\d+)", text)
            if m and m.group(1) not in created:
                created[m.group(1)] = t
            m2 = re.search(r"(T-\d+)", text)
            if m2 and m2.group(1) not in first_seen:
                first_seen[m2.group(1)] = t
            m3 = re.match(r"DONE (T-\d+)", text)
            if m3:
                closed[m3.group(1)] = t
        except Exception:
            continue
    mids = sorted({t.get("milestone", "") for t in board_tasks if t.get("milestone")},
                  key=lambda m: (int(re.sub(r"\D", "", m) or 0), m))
    # exclude dropped tasks (unknown close time)
    usable = [t for t in board_tasks if isinstance(t, dict) and t.get("status") != "dropped"
              and t.get("id") and t.get("milestone")]
    bh = 1 if hours in (6, 24) else 6
    n = max(1, hours // bh)
    points = []
    for i in range(n + 1):
        pt = start + dt.timedelta(hours=i * bh)
        if pt > now:
            pt = now
        vals = {}
        for mid in mids:
            c = 0
            for t in usable:
                if t.get("milestone") != mid:
                    continue
                tid = t.get("id")
                cr = created.get(tid, first_seen.get(tid, start))
                if cr is None:
                    cr = start
                cl = closed.get(tid)
                if cr <= pt and (cl is None or cl > pt):
                    c += 1
            vals[mid] = c
        points.append({"t": pt.strftime(TIME_FMT), "open": vals})
    return {"milestones": mids, "series": points}


def _eta(board_tasks: list, done: list[dt.datetime], now: dt.datetime) -> dict:
    cutoff = now - dt.timedelta(hours=12)
    recent = [d for d in done if d >= cutoff]
    rate = len(recent) / 12 if recent else 0.0
    # current milestone: first with remaining work
    by_mid: dict[str, dict] = {}
    for t in board_tasks:
        if not isinstance(t, dict):
            continue
        mid = t.get("milestone") or ""
        d = by_mid.setdefault(mid, {"remaining": 0})
        if t.get("status") not in ("done", "dropped"):
            d["remaining"] += 1
    mids = sorted(by_mid, key=lambda m: (int(re.sub(r"\D", "", m) or 0), m))
    cur = next((m for m in mids if by_mid[m]["remaining"] > 0), mids[0] if mids else "")
    total_rem = sum(v["remaining"] for v in by_mid.values())

    def label(rem: int) -> dict:
        if rate == 0:
            return {"remaining": rem, "label": "—", "low": False}
        h = rem / rate if rate else None
        return {"remaining": rem, "label": f"~{h:.1f} h",
                "low": len(recent) < 5,
                "eta_hours": round(h, 1) if h is not None else None}

    m_lab = label(by_mid.get(cur, {}).get("remaining", 0))
    b_lab = label(total_rem)
    m_lab["id"] = cur
    return {"milestone": m_lab, "board": b_lab,
            "done_12h": len(recent), "rate_per_hour": round(rate, 3)}


# ------------------------------------------------------------------ gantt (S3)

def _parse_until(text: str, when: dt.datetime) -> dt.datetime:
    m = re.search(r"until ~(?:\w{3} )?(\d{1,2}):(\d{2})", text)
    if m:
        try:
            u = when.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            if u < when:
                u += dt.timedelta(days=1)
            return u
        except ValueError:
            pass
    return when + dt.timedelta(hours=1)


def _account_of(agent_or_acct: str, agents: dict) -> str:
    if agent_or_acct in agents:
        return (agents[agent_or_acct] or {}).get("account", agent_or_acct)
    # maybe already an account id
    accts = {(a or {}).get("account", n) for n, a in agents.items()}
    if agent_or_acct in accts:
        return agent_or_acct
    return agent_or_acct


def _gantt(events: list[tuple[dt.datetime, str]], board_tasks: list,
           agents: dict, now: dt.datetime,
           start: dt.datetime) -> dict:
    by_id = {t.get("id"): t for t in board_tasks if isinstance(t, dict) and t.get("id")}
    # lanes from START
    lanes: dict[str, list] = {}
    opens: dict[tuple[str, str], tuple[dt.datetime, str, str]] = {}  # (lane, task) -> (start, title, lane)
    bars_by_lane: dict[str, list] = {}
    for t, text in sorted(events, key=lambda e: e[0]):
        try:
            m = re.match(r"START (T-\d+) \[lane (\w)\](?: \[([^\]/]+)(?:/([^\]]+))?\])? (.*)", text)
            if m:
                tid, lane = m.group(1), m.group(2)
                title = (m.group(5) or "").strip()
                opens[(lane, tid)] = (t, title, lane)
                lanes.setdefault(lane, [])
                continue
            m2 = re.match(r"(DONE|BLOCKED) (T-\d+)", text)
            m3 = re.match(r"RECOVER (T-\d+)", text)
            end_tid = None
            outcome = None
            if m2:
                outcome = "done" if m2.group(1) == "DONE" else "blocked"
                end_tid = m2.group(2)
            elif m3:
                outcome = "recover"
                end_tid = m3.group(1)
            if end_tid:
                # close any open bar for this task (any lane)
                for key in [k for k in opens if k[1] == end_tid]:
                    st, title, lane = opens.pop(key)
                    if st < start and t < start:
                        continue
                    eff_start = max(st, start)
                    task = by_id.get(end_tid, {})
                    bars_by_lane.setdefault(lane, []).append({
                        "task": end_tid, "title": title,
                        "start": eff_start.strftime(TIME_FMT),
                        "end": t.strftime(TIME_FMT),
                        "outcome": outcome,
                        "attempts": task.get("attempts", 0),
                        "duration_min": round((t - st).total_seconds() / 60, 1),
                    })
        except Exception:
            continue
    for (lane, tid), (st, title, _l) in list(opens.items()):
        try:
            if now < start:
                continue
            eff_start = max(st, start)
            if st > now:
                continue
            task = by_id.get(tid, {})
            bars_by_lane.setdefault(lane, []).append({
                "task": tid, "title": title,
                "start": eff_start.strftime(TIME_FMT),
                "end": now.strftime(TIME_FMT),
                "outcome": "running",
                "attempts": task.get("attempts", 0),
                "duration_min": round((now - st).total_seconds() / 60, 1),
            })
        except Exception:
            continue
    lane_rows = [{"lane": ln, "bars": sorted(bars_by_lane.get(ln, []), key=lambda b: b["start"])}
                 for ln in sorted(set(list(lanes) + list(bars_by_lane)))]
    # naps per account
    limits_ev: list[tuple[dt.datetime, str, str, dt.datetime]] = []  # (start, kind, account, until)
    restores: list[tuple[dt.datetime, str]] = []
    for t, text in events:
        try:
            m = re.match(r"QUOTA RESTORED (\S+)", text)
            if m:
                restores.append((t, m.group(1)))
                continue
            m = re.match(r"USAGE LIMIT (\S+)", text)
            if m:
                subj = m.group(1)
                acct = _account_of(subj, agents)
                limits_ev.append((t, "USAGE LIMIT", acct, _parse_until(text, t)))
                continue
            m = re.match(r"PREEMPTIVE HANDOFF (\S+)", text)
            if m:
                acct = _account_of(m.group(1), agents)
                limits_ev.append((t, "PREEMPTIVE HANDOFF", acct, _parse_until(text, t)))
                continue
            m = re.match(r"PROVIDER DOWN (\S+)", text)
            if m:
                acct = _account_of(m.group(1), agents)
                limits_ev.append((t, "PROVIDER DOWN", acct, _parse_until(text, t)))
                continue
        except Exception:
            continue
    naps: dict[str, list] = {}
    for st, kind, acct, until in limits_ev:
        try:
            if until < start or st > now:
                continue
            end = until
            for rt, racc in sorted(restores):
                if rt > st and (racc == acct or _account_of(racc, agents) == acct):
                    if rt < end:
                        end = rt
                    break
            if end > now:
                end = min(end, now)
            eff_start = max(st, start)
            if end <= eff_start:
                continue
            naps.setdefault(acct, []).append({
                "start": eff_start.strftime(TIME_FMT),
                "end": end.strftime(TIME_FMT),
                "reason": kind,
                "hours": round((end - eff_start).total_seconds() / 3600, 2),
            })
        except Exception:
            continue
    nap_rows = [{"account": a, "bars": sorted(v, key=lambda b: b["start"])} for a, v in sorted(naps.items())]
    return {"lanes": lane_rows, "naps": nap_rows, "now": now.strftime(TIME_FMT)}


# ------------------------------------------------------------------ routing (S4)

def _routing(events: list[tuple[dt.datetime, str]], agents: dict,
             start: dt.datetime, now: dt.datetime) -> dict:
    flows: dict[tuple[str, str], int] = {}
    counts: dict[str, dict] = {}

    def cnt(a: str) -> dict:
        return counts.setdefault(a, {"usage_limit": 0, "preemptive": 0,
                                     "provider_down": 0, "model_gone": 0,
                                     "quick_fail": 0, "agent_fail": 0})

    for a in agents:
        cnt(a)
    for t, text in events:
        try:
            if t < start or t > now:
                continue
            m = re.match(r"FALLBACK (\S+) is limited until [^;]+; (\S+) handles", text)
            if m:
                lim, sub = m.group(1), m.group(2)
                flows[(lim, sub)] = flows.get((lim, sub), 0) + 1
                continue
            m = re.match(r"USAGE LIMIT (\S+)", text)
            if m and m.group(1) in counts:
                counts[m.group(1)]["usage_limit"] += 1
                continue
            m = re.match(r"PREEMPTIVE HANDOFF (\S+)", text)
            if m:
                subj = m.group(1)
                # attribute to every agent on that account (or the agent itself)
                matched = [a for a, cfg in agents.items()
                           if (cfg or {}).get("account", a) == subj or a == subj]
                for a in matched or ([subj] if subj in counts else []):
                    cnt(a)["preemptive"] += 1
                continue
            m = re.match(r"PROVIDER DOWN (\S+)", text)
            if m and m.group(1) in counts:
                counts[m.group(1)]["provider_down"] += 1
                continue
            m = re.match(r"MODEL GONE (\S+)", text)
            if m and m.group(1) in counts:
                counts[m.group(1)]["model_gone"] += 1
                continue
            m = re.match(r"QUICK FAIL (\S+)", text)
            if m and m.group(1) in counts:
                counts[m.group(1)]["quick_fail"] += 1
                continue
            m = re.match(r"AGENT FAIL (\S+)", text)
            if m and m.group(1) in counts:
                counts[m.group(1)]["agent_fail"] += 1
                continue
        except Exception:
            continue
    return {"flows": [{"from": k[0], "to": k[1], "count": v}
                      for k, v in sorted(flows.items())],
            "counts": counts}


# ------------------------------------------------------------------ quota (S5a)

def _quota(events: list[tuple[dt.datetime, str]], agents: dict,
           start: dt.datetime, now: dt.datetime, gantt_naps: list) -> dict:
    # current state: reuse server.limits logic (reimplemented on whole tail)
    # here: state at now from all events (not just window)
    cur = _current_limits(events, agents, now)
    hours_by_acct: dict[str, float] = {}
    n_by_acct: dict[str, int] = {}
    for row in gantt_naps:
        acct = row.get("account")
        bars = row.get("bars", [])
        n_by_acct[acct] = len(bars)
        hours_by_acct[acct] = round(sum(b.get("hours", 0) for b in bars), 2)
    accts = set()
    for a, cfg in agents.items():
        accts.add((cfg or {}).get("account", a))
    for row in gantt_naps:
        accts.add(row.get("account"))
    out = []
    for acct in sorted(accts):
        st = cur.get(acct, {})
        # cur is keyed by agent; map to account
        out.append({"id": acct,
                    "state": st.get("state", "ok"),
                    "until": st.get("until", ""),
                    "limits": n_by_acct.get(acct, 0),
                    "hours_limited": hours_by_acct.get(acct, 0.0)})
    # fix state per account: worst among member agents
    sev = {"gone": 3, "down": 2, "limited": 1}
    for row in out:
        members = [a for a, cfg in agents.items() if (cfg or {}).get("account", a) == row["id"]]
        best = None
        for m in members:
            if m in cur:
                if best is None or sev.get(cur[m]["state"], 0) > sev.get(best["state"], 0):
                    best = {"state": cur[m]["state"], "until": cur[m].get("until", "")}
        if best:
            row["state"] = best["state"]
            row["until"] = best["until"]
    return {"accounts": out}


def _current_limits(events: list[tuple[dt.datetime, str]], agents: dict,
                    now: dt.datetime) -> dict:
    account = {n: (a or {}).get("account", n) for n, a in agents.items()}
    out: dict = {}
    for when, line in sorted(events, key=lambda e: e[0]):
        try:
            m = re.match(r"(USAGE LIMIT|PROVIDER DOWN|MODEL GONE|PREEMPTIVE HANDOFF|QUOTA RESTORED) (\S+)", line)
            # events have timestamp stripped; line starts with keyword
            if not m:
                continue
            kind_word, subj = m.group(1), m.group(2)
            if kind_word == "QUOTA RESTORED":
                out = {k: v for k, v in out.items()
                       if account.get(k) != subj and k != subj}
                continue
            until = _parse_until(line, when)
            kind = {"USAGE LIMIT": "limited", "PREEMPTIVE HANDOFF": "limited",
                    "PROVIDER DOWN": "down", "MODEL GONE": "gone"}[kind_word]
            if kind == "limited":
                acct = account.get(subj, subj)
                for other, other_acct in account.items():
                    if other_acct == acct:
                        out[other] = {"state": kind, "until": until}
            elif subj in agents:
                out[subj] = {"state": kind, "until": until}
        except Exception:
            continue
    return {k: {"state": v["state"], "until": v["until"].strftime("%H:%M")}
            for k, v in out.items() if v["until"] > now}


# ------------------------------------------------------------------ incidents (S6) + plans

def _incidents(events: list[tuple[dt.datetime, str]]) -> dict:
    items = []
    counts: dict[str, int] = {}
    pending: dict[str, tuple[dt.datetime, str]] = {}  # agent -> (called_time, reason)
    for t, text in sorted(events, key=lambda e: e[0]):
        try:
            m = re.match(r"SUPERVISOR-AI (\S+) called: (.*)", text)
            if m:
                agent = m.group(1)
                reason = m.group(2)
                # strip trailing (log ...) for reason display
                reason = re.sub(r"\s*\(log .*\)\s*$", "", reason).strip()
                pending[agent] = (t, reason)
                continue
            m = re.match(r"SUPERVISOR-AI (\S+) (done|timed out|unavailable|finished)", text)
            if m:
                agent = m.group(1)
                if agent in pending:
                    st, reason = pending.pop(agent)
                    word = m.group(2)
                    outcome = {"done": "done", "timed": "timed out",
                               "unavailable": "unavailable", "finished": "finished without report"}[word]
                    summary = text.split(":", 1)[1].strip() if ":" in text else text
                    if outcome == "timed out":
                        summary = text.strip()
                    dur = round((t - st).total_seconds() / 60, 1)
                    items.append({"time": t.strftime(TIME_FMT), "type": "supervisor_ai",
                                        "agent": agent, "reason": reason, "outcome": outcome,
                                        "summary": summary[:300], "duration_min": dur})
                    counts["supervisor_ai"] = counts.get("supervisor_ai", 0) + 1
                continue
            if text.startswith("SUPERVISOR relaunched"):
                items.append({"time": t.strftime(TIME_FMT), "type": "supervisor_relaunched",
                              "reason": text, "outcome": "info", "summary": text[:300],
                              "duration_min": None})
                counts["supervisor_relaunched"] = counts.get("supervisor_relaunched", 0) + 1
            elif text.startswith("ORCHESTRATOR ERROR"):
                items.append({"time": t.strftime(TIME_FMT), "type": "orchestrator_error",
                              "reason": text, "outcome": "error", "summary": text[:300],
                              "duration_min": None})
                counts["orchestrator_error"] = counts.get("orchestrator_error", 0) + 1
            elif re.match(r"LANE \w+ ERROR", text):
                items.append({"time": t.strftime(TIME_FMT), "type": "lane_error",
                              "reason": text, "outcome": "error", "summary": text[:300],
                              "duration_min": None})
                counts["lane_error"] = counts.get("lane_error", 0) + 1
            elif text.startswith("PLANNER ERROR"):
                items.append({"time": t.strftime(TIME_FMT), "type": "planner_error",
                              "reason": text, "outcome": "error", "summary": text[:300],
                              "duration_min": None})
                counts["planner_error"] = counts.get("planner_error", 0) + 1
            elif "WATCHDOG" in text:
                items.append({"time": t.strftime(TIME_FMT), "type": "watchdog",
                              "reason": text, "outcome": "info", "summary": text[:300],
                              "duration_min": None})
                counts["watchdog"] = counts.get("watchdog", 0) + 1
            elif text.startswith("RECOVER "):
                items.append({"time": t.strftime(TIME_FMT), "type": "recover",
                              "reason": text, "outcome": "info", "summary": text[:300],
                              "duration_min": None})
                counts["recover"] = counts.get("recover", 0) + 1
        except Exception:
            continue
    for agent, (st, reason) in pending.items():
        items.append({"time": st.strftime(TIME_FMT), "type": "supervisor_ai",
                      "agent": agent, "reason": reason, "outcome": "in progress",
                      "summary": "", "duration_min": None})
        counts["supervisor_ai"] = counts.get("supervisor_ai", 0) + 1
    items.sort(key=lambda d: d["time"], reverse=True)
    return {"counts": counts, "items": items}


def _plans(events: list[tuple[dt.datetime, str]]) -> list[dict]:
    out = []
    pending: tuple[dt.datetime, str] | None = None
    for t, text in sorted(events, key=lambda e: e[0]):
        try:
            m = re.match(r"PLAN start \((.*)\)", text)
            if m:
                pending = (t, m.group(1))
                continue
            m = re.match(r"PLAN done: (.*)", text)
            if m:
                if pending:
                    st, reason = pending
                    pending = None
                    out.append({"time": st.strftime(TIME_FMT), "reason": reason,
                                "duration_min": round((t - st).total_seconds() / 60, 1),
                                "summary": m.group(1)[:500]})
                else:
                    out.append({"time": t.strftime(TIME_FMT), "reason": "",
                                "duration_min": None, "summary": m.group(1)[:500]})
        except Exception:
            continue
    if pending:
        st, reason = pending
        out.append({"time": st.strftime(TIME_FMT), "reason": reason,
                    "duration_min": None, "summary": ""})
    out.sort(key=lambda d: d["time"], reverse=True)
    return out


def build_notes(root: Path) -> dict:
    """Plans + notes docs list for GET /api/notes."""
    events = _events(root)
    plans = _plans(events)
    docs = []
    for name, rel in (("decisions", "project/decisions.md"),
                      ("assumptions", "project/assumptions.md"),
                      ("PM notes", "project/PM_NOTES.md")):
        p = root / rel
        try:
            mt = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime(TIME_FMT) if p.is_file() else ""
        except OSError:
            mt = ""
        docs.append({"name": name, "path": rel, "mtime": mt})
    try:
        msdir = root / "project" / "milestones"
        ms = sorted(msdir.glob("*.md")) if msdir.is_dir() else []
    except OSError:
        ms = []
    for p in ms:
        try:
            mt = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime(TIME_FMT)
        except OSError:
            mt = ""
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        docs.append({"name": f"milestone {p.stem}", "path": rel, "mtime": mt})
    return {"plans": plans, "docs": docs}


# ------------------------------------------------------------------ top-level

def build_stats(root: Path, now: dt.datetime, hours: int) -> dict:
    """Parse the WHOLE events.log + board.json and build windowed stats."""
    if hours not in ALLOWED_HOURS:
        raise ValueError("bad hours")
    root = Path(root)
    events = _events(root)
    board = _board(root)
    agents = _agents(root)
    tasks = [t for t in board.get("tasks", []) if isinstance(t, dict)]
    start = now - dt.timedelta(hours=hours)
    windowed = [(t, x) for t, x in events if start <= t <= now]

    _attach_work_minutes(tasks, events)

    def hist_in(h_at: str, window: bool) -> bool:
        if not window:
            return True
        try:
            at = parse_time(h_at) if isinstance(h_at, str) else None
        except Exception:
            at = None
        if at is None:
            return False
        return start <= at <= now

    # windowed + all-time history entries
    all_entries: list[tuple[dict, dict]] = []
    win_entries: list[tuple[dict, dict]] = []
    for task in tasks:
        hist = task.get("history") or []
        if not isinstance(hist, list):
            continue
        for h in hist:
            if not isinstance(h, dict):
                continue
            all_entries.append((task, h))
            if hist_in(h.get("at", ""), True):
                win_entries.append((task, h))
    # fallbacks
    all_fb, win_fb = [], []
    for t, text in events:
        try:
            m = re.match(r"FALLBACK (\S+) is limited until [^;]+; (\S+) handles", text)
            if m:
                pair = (m.group(1), m.group(2))
                all_fb.append(pair)
                if start <= t <= now:
                    win_fb.append(pair)
        except Exception:
            continue
    # blocked workers: tasks with status blocked
    blocked_all: dict[str, list] = {}
    blocked_win: dict[str, list] = {}
    for task in tasks:
        if task.get("status") != "blocked":
            continue
        workers = [h.get("worker") for h in (task.get("history") or [])
                   if isinstance(h, dict) and isinstance(h.get("worker"), str)]
        if workers:
            blocked_all[task.get("id")] = workers
            # windowed: only if task has recent activity? use any history at in window
            hist = task.get("history") or []
            recent = any(hist_in(h.get("at", ""), True) for h in hist if isinstance(h, dict))
            # also include if BLOCKED event in window
            if recent:
                blocked_win[task.get("id")] = workers
            else:
                # check BLOCKED event time
                for t, text in windowed:
                    if text.startswith(f"BLOCKED {task.get('id')}"):
                        blocked_win[task.get("id")] = workers
                        break
    score_all = _scorecards_for(all_entries, agents, all_fb, blocked_all)
    score_win = _scorecards_for(win_entries, agents, win_fb, blocked_win)

    done_all = _done_times(events)
    done_win = [d for d in done_all if start <= d <= now]
    throughput = _throughput(done_win, start, now, hours)
    burndown = _burndown(tasks, events, start, now, hours)
    eta = _eta(tasks, done_all, now)
    gantt = _gantt(events, tasks, agents, now, start)
    routing = _routing(events, agents, start, now)
    quota = _quota(events, agents, start, now, gantt["naps"])
    incidents = _incidents(windowed)
    return {"hours": hours, "now": now.strftime(TIME_FMT),
            "window_start": start.strftime(TIME_FMT),
            "scorecards": score_win, "scorecards_all": score_all,
            "throughput": throughput, "burndown": burndown, "eta": eta,
            "gantt": gantt, "routing": routing, "quota": quota,
            "incidents": incidents}
