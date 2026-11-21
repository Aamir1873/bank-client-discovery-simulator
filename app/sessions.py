"""Interviews in server memory, and everything the routes do with them.

No database: an interview lives here, keyed by a random id, until the server restarts. The hidden needs, the
opened list and need ids stay on the server; the browser only ever gets what the public functions return.
Every function raises ApiError with a plain sentence the page can show as is.
"""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

from . import ai, content

MAX_TURNS = 30        # messages both ways
MAX_HINTS = 2
MAX_MESSAGE = 1000    # characters
MAX_SUMMARY = 3000
MAX_REASON = 500
MAX_AGE = 6 * 60 * 60  # seconds; older interviews are dropped when a new one starts
BUSY = "Your last message is still being answered. Wait for the reply, then send the next one."


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Interview:
    id: str
    client_id: str
    history: list = field(default_factory=list)
    opened: list = field(default_factory=list)
    opened_at: dict = field(default_factory=dict)  # need id -> index in history of the student message that opened it
    busy: threading.Lock = field(default_factory=threading.Lock, repr=False)
    hints_used: int = 0
    hinted: list = field(default_factory=list)  # needs a hint already pointed at, so the next one differs
    created: float = field(default_factory=time.time)
    summary: str = ""
    picks: list = field(default_factory=list)
    feedback: dict | None = None


_STORE: dict[str, Interview] = {}
_LOCK = threading.Lock()


def _client(client_id: str) -> dict:
    try:
        return content.load_client(client_id)
    except content.ContentError as e:
        if str(e).startswith("Unknown client"):
            raise ApiError(404, "That client doesn't exist. Go back and pick a client from the list.")
        raise ApiError(500, f"A content file is broken: {e}")


def _get(iid: str) -> Interview:
    iv = _STORE.get(iid)
    if not iv:
        raise ApiError(404, "This interview has ended or the server restarted. Pick a client to start again.")
    return iv


@contextmanager
def _working(iv: Interview):
    """One request at a time per interview, held across the model call, so two tabs can't lose a turn."""
    if not iv.busy.acquire(blocking=False):
        raise ApiError(409, BUSY)
    try:
        yield
    finally:
        iv.busy.release()


# ---- public data -------------------------------------------------------------------------------

def list_clients() -> list[dict]:
    out = []
    for cid in content.client_ids():
        c = _client(cid)
        out.append({k: c[k] for k in ("id", "name", "intro", "difficulty", "opening_line")})
    return out


def get_client(client_id: str) -> dict:
    return content.public_client(_client(client_id))


def get_products() -> dict:
    return content.load_catalogue()


# ---- the interview -----------------------------------------------------------------------------

def start(client_id: str) -> dict:
    client = _client(client_id)
    iv = Interview(id=uuid.uuid4().hex, client_id=client_id)
    with _LOCK:
        cutoff = time.time() - MAX_AGE
        for old in [k for k, v in _STORE.items() if v.created < cutoff]:
            del _STORE[old]
        _STORE[iv.id] = iv
    return {"interview_id": iv.id, "client": content.public_client(client), "max_turns": MAX_TURNS, "hints_left": MAX_HINTS}


def send(iid: str, text: str) -> dict:
    iv = _get(iid)
    text = (text or "").strip()
    if not text:
        raise ApiError(400, "Type a message before sending.")
    if len(text) > MAX_MESSAGE:
        raise ApiError(400, f"That message is too long. Keep it under {MAX_MESSAGE} characters.")
    if iv.feedback is not None:
        raise ApiError(400, "This interview is finished. Start a new one to keep practising.")
    if len(iv.history) + 2 > MAX_TURNS:
        raise ApiError(400, "You've reached the message limit. End the interview to get feedback.")
    client = _client(iv.client_id)
    with _working(iv):
        history = iv.history + [{"role": "user", "content": text}]
        reply, opened, new = ai.turn(client, history, iv.opened)  # AIError goes up; nothing is saved
        if new:
            iv.opened_at[new] = len(history) - 1
        iv.history = history + [{"role": "assistant", "content": reply}]
        iv.opened = opened
    return {"reply": reply, "turns": len(iv.history), "max_turns": MAX_TURNS}


def hint(iid: str) -> dict:
    iv = _get(iid)
    if iv.hints_used >= MAX_HINTS:
        raise ApiError(400, "You've used both hints for this interview.")
    if not iv.history:
        raise ApiError(400, "Ask the client something first, then ask for a hint.")
    with _working(iv):
        h = ai.hint(_client(iv.client_id), set(iv.opened), set(iv.hinted))
        iv.hints_used += 1
        if h.get("target"):
            iv.hinted.append(h["target"])
    return {"found": int(h["found"]), "total": int(h["total"]), "nudge": str(h["nudge"]), "hints_left": MAX_HINTS - iv.hints_used}


def feedback(iid: str, summary: str, picks: list[dict]) -> dict:
    iv = _get(iid)
    if not iv.history:
        raise ApiError(400, "Talk to the client before asking for feedback.")
    summary = (summary or "").strip()
    if len(summary) > MAX_SUMMARY:
        raise ApiError(400, f"The summary is too long. Keep it under {MAX_SUMMARY} characters.")
    known = {p["id"] for p in content.load_catalogue()["products"]}
    clean, seen = [], set()
    for p in picks or []:
        pid = str((p or {}).get("product_id", ""))
        if pid not in known:
            raise ApiError(400, "One of the picked products doesn't exist. Reload the page and pick again.")
        if pid in seen:
            continue
        seen.add(pid)
        clean.append({"product_id": pid, "reason": str(p.get("reason") or "").strip()[:MAX_REASON]})
    asked = {nid: iv.history[i]["content"] for nid, i in iv.opened_at.items()}
    with _working(iv):
        result = ai.coach(_client(iv.client_id), iv.history, summary, clean, iv.hints_used, asked)
        result.update({"hints_used": iv.hints_used, "turns": len(iv.history)})
        iv.summary, iv.picks, iv.feedback = summary, clean, result
    return result


def export(iid: str) -> tuple[str, str]:
    """(file name, Markdown) for the whole session."""
    iv = _get(iid)
    client = _client(iv.client_id)
    lines = [f"# Practice interview: {client['name']}", "", f"{client['intro']}.", "", "## Conversation", ""]
    for m in iv.history:
        who = "Banker" if m["role"] == "user" else client["name"]
        lines.append(f"**{who}:** {m['content']}")
        lines.append("")
    lines += ["## Summary", "", iv.summary or "_Not written._", "", "## Products recommended", ""]
    names = {p["id"]: p["name"] for p in content.load_catalogue()["products"]}
    lines += [f"- **{names.get(p['product_id'], p['product_id'])}**: {p['reason'] or '_no reason given_'}" for p in iv.picks] or ["_None picked._"]
    fb = iv.feedback
    if fb:
        lines += ["", "## Coach feedback", "", f"Needs found: {fb['found']} of {fb['total']}. Hints used: {iv.hints_used}.", ""]
        for n in fb["needs"]:
            mark = "Found" if n["found"] else "Missed"
            extra = f' (you asked: "{n["quote"]}")' if n["found"] and n["quote"] else (f" Try: {n['better_question']}" if n["better_question"] else "")
            lines.append(f"- {mark}: {n['label']}. {n['fact']}{extra}")
        lines += ["", "**Your picks**", ""]
        lines += [f"- {p['name']}: {'fits' if p['fits'] else 'does not fit'}. {p['why']}" for p in fb["picks"]] or ["- None"]
        for key, title in (("went_well", "What went well"), ("missed", "What was missed"), ("improve", "How to improve")):
            lines += ["", f"**{title}**", ""] + [f"- {x}" for x in fb[key]]
    else:
        lines += ["", "_No feedback yet._"]
    return f"interview-{client['id']}.md", "\n".join(lines) + "\n"


def reset() -> None:
    """For tests."""
    with _LOCK:
        _STORE.clear()
