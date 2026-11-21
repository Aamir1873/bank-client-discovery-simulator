"""The AI jobs.

Each student message:  gate (does it open a hidden need?)  ->  client reply (knows only the opened needs).
In the app, "found" is what the gate opened: the hint and the coach count from it, so they always agree and
cost no extra model calls. The judge (one yes/no per need, with a quote the code verifies) is kept for the
leak test and the re-score script, which need a check that is independent of the gate.
"""
from __future__ import annotations

import re

from . import content
from .llm import AIError, chat, coach_model, parse_json, setting


def gate(client: dict, history: list[dict], opened: list[str]) -> str | None:
    """Which still-hidden need the latest student message opens, if any. At most one per turn."""
    prompt = content.gate_prompt(client, opened, history)
    if not prompt:
        return None
    closed = {n["id"] for n in client["hidden_needs"]} - set(opened)
    message = history[-1]["content"] if history else ""
    needs = content.needs_by_id(client)
    for _ in range(2):
        try:
            data = parse_json(chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=60, json_mode=True))
            pick = data.get("opens")
        except AIError:
            continue
        # The gate model is accurate (it opened no wrong need in 80 reworded questions), so trust its pick.
        # Only a message aimed at the gate itself is refused, so a student can't talk it into opening a need.
        if pick in closed and not aimed_at_gate(message):
            return pick
        return None
    # The gate failed twice: fall back to the need's keywords in the student's message.
    for n in client["hidden_needs"]:
        # Two keyword hits, not one: single words like "prefer" or "home" also appear in vague questions.
        if n["id"] in closed and keyword_hits(n, message) >= 2:
            return n["id"]
    return None


GATE_WORDS = ("classifier", "system prompt", "topic id", "ignore your instructions", "ignore all previous", "ignore previous instructions")


def aimed_at_gate(message: str) -> bool:
    """True if the message talks to the machinery rather than to the client."""
    text = message.lower()
    return any(w in text for w in GATE_WORDS)


def keyword_hits(need: dict, message: str) -> int:
    """How many of the need's keywords start a word in the message ("cost" matches "costs")."""
    text = message.lower()
    return sum(bool(re.search(r"\b" + re.escape(str(k).lower()), text)) for k in need["keywords"])


def client_reply(client: dict, history: list[dict], opened: list[str], answer_now: str | None = None) -> str:
    system = content.client_system_prompt(client, opened, answer_now)
    messages = [{"role": "system", "content": system}] + history
    if answer_now:
        # Small models follow the last instruction best, so repeat the unlocked fact right before the reply.
        fact = content.needs_by_id(client)[answer_now]["fact"].strip()
        messages.append({"role": "system", "content": f"In this reply, tell the banker this plainly, in your own words: {fact}"})
    return chat(messages, temperature=float(setting("CLIENT_TEMPERATURE", "0.5")), max_tokens=220)


def turn(client: dict, history: list[dict], opened: list[str]) -> tuple[str, list[str], str | None]:  # noqa: D401
    """One student message in, the client's reply out. Returns (reply, opened needs after this turn, need just opened)."""
    new = gate(client, history, opened)
    opened = opened + [new] if new else list(opened)
    return client_reply(client, history, opened, new), opened, new


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def quote_matches(quote: str, said: str, share: float = 0.8) -> bool:
    """True if most of the quote's words appear in what the client said. Small judges paraphrase a
    little when they copy, so exact matching throws away true finds."""
    words = [w for w in _norm(quote).split() if len(w) > 2]
    if len(words) < 4:  # a word or two ("loan", "money") proves nothing
        return False
    have = set(_norm(said).split())
    return sum(w in have for w in words) / len(words) >= share


def judge_detail(client: dict, history: list[dict], need: dict) -> tuple[bool, int, str]:
    """Did the client actually say this need? Returns (found, index of the client line in history, quote).
    The judge names a line; the quote must be in that line."""
    said = [(i, m["content"]) for i, m in enumerate(history) if m["role"] == "assistant"]
    if not said:
        return False, -1, ""
    lines = "\n".join(f"{k + 1}. {t}" for k, (_, t) in enumerate(said))
    prompt = content.render("judge", lines=lines, label=need["label"], fact=need["fact"].strip())
    for _ in range(2):
        try:
            data = parse_json(chat([{"role": "user", "content": prompt}], model=coach_model(), temperature=0, max_tokens=150, json_mode=True))
            n = int(data.get("line") or 0)
        except (AIError, ValueError, TypeError):
            continue
        if not 1 <= n <= len(said):
            return False, -1, ""
        idx, text = said[n - 1]
        quote = str(data.get("quote", ""))
        return (True, idx, quote) if quote_matches(quote, text) else (False, -1, "")
    raise AIError(f"The found check gave no usable answer for {need['id']}")


def judge_need(client: dict, history: list[dict], need: dict) -> bool:
    return judge_detail(client, history, need)[0]


def found_details(client: dict, history: list[dict]) -> list[dict]:
    """One entry per hidden need, in file order: found, and the student's question that brought it out."""
    out = []
    for n in client["hidden_needs"]:
        found, idx, _ = judge_detail(client, history, n)
        asked = ""
        if found:
            asked = next((history[j]["content"] for j in range(idx - 1, -1, -1) if history[j]["role"] == "user"), "")
        out.append({"id": n["id"], "found": found, "asked": asked})
    return out


def found_check(client: dict, history: list[dict]) -> list[str]:
    """The ids of the needs found. The leak test and the re-score script use this."""
    return [d["id"] for d in found_details(client, history) if d["found"]]


_RANK = {"critical": 0, "moderate": 1}


def hint(client: dict, found: set[str], hinted: set[str] = frozenset()) -> dict:
    """Count found plus one nudge. `found` is what the gate has opened. The nudge model only ever sees the
    topic of one need that is still hidden, never a fact, so it cannot give the answer away."""
    left = sorted((n for n in client["hidden_needs"] if n["id"] not in found), key=lambda n: _RANK.get(n["importance"], 9))
    total = len(client["hidden_needs"])
    done = total - len(left)
    if not left:
        return {"found": total, "total": total, "nudge": "You've covered the main areas. You can move to the wrap-up."}
    # A second hint points at an area not hinted before, when there is one left.
    target = next((n for n in left if n["id"] not in hinted), left[0])
    prompt = content.render("hint", name=client["name"], topic=target["reveal_when"])
    try:
        nudge = str(parse_json(chat([{"role": "user", "content": prompt}], model=coach_model(), temperature=0.3, max_tokens=120, json_mode=True)).get("nudge", "")).strip()
    except AIError:
        nudge = ""
    return {"found": done, "total": total, "target": target["id"],
            "nudge": nudge or "Try an area of their life or business you haven't asked about yet."}


# ---- the coach ---------------------------------------------------------------------------------

def pick_fits(pid: str, suitable: set[str], unsuitable: dict, model_says) -> bool:
    """The client file decides; the model's view counts only for products the file says nothing about,
    and only if it is exactly True (a string "false" must not count as fitting)."""
    if pid in unsuitable:
        return False
    if pid in suitable:
        return True
    return model_says is True


def _valid_coach(data: dict, missed: list[str], pick_ids: list[str]) -> bool:
    if not isinstance(data, dict):
        return False
    for key in ("went_well", "missed", "improve"):
        if not isinstance(data.get(key), list) or not data[key] or not all(isinstance(x, str) and x.strip() for x in data[key]):
            return False  # each of the three areas needs at least one real point
    if not isinstance(data.get("better_questions"), dict) or not isinstance(data.get("picks"), list):
        return False
    return all(isinstance(p, dict) and "id" in p and "fits" in p for p in data["picks"])


def coach(client: dict, history: list[dict], summary: str, picks: list[dict], hints_used: int,
          asked: dict[str, str]) -> dict:
    """Structured feedback. `asked` maps each need the gate opened to the student's message that opened it;
    the coach model never decides what was found, and pick verdicts come from the client file."""
    catalogue = content.load_catalogue()
    products = {p["id"]: p for p in catalogue["products"]}
    needs = [{"id": n["id"], "found": n["id"] in asked, "asked": asked.get(n["id"], "")} for n in client["hidden_needs"]]
    by_id = content.needs_by_id(client)
    missed = [d["id"] for d in needs if not d["found"]]
    found_text = "\n".join(
        f"- {d['id']} ({by_id[d['id']]['label']}): {'FOUND, the trainee asked: ' + repr(d['asked']) if d['found'] else 'MISSED'}"
        for d in needs)
    picks_text = "\n".join(f"- {p['product_id']} ({products[p['product_id']]['name']}): {p.get('reason') or '(no reason given)'}" for p in picks) or "- None picked"
    unsuitable = {u["id"]: u["why"] for u in client.get("unsuitable_products", [])}
    client_file = (
        f"Name: {client['name']}\nWho: {client['intro']}\nBackground: {client['background'].strip()}\n"
        f"Hidden needs:\n" + "\n".join(f"- {n['id']} ({n['label']}): {n['fact'].strip()}" for n in client["hidden_needs"])
        + f"\nSuitable products: {', '.join(client.get('suitable_products', [])) or 'none'}\n"
        + "Unsuitable products:\n" + ("\n".join(f"- {k}: {v}" for k, v in unsuitable.items()) or "- none"))
    prompt = content.render(
        "coach",
        client_file=client_file,
        products=content.products_text(catalogue),
        transcript=content.transcript_text(history, client["name"]),
        found=found_text,
        summary=summary.strip() or "(no summary written)",
        picks=picks_text,
        hints_used=str(hints_used),
    )
    pick_ids = [p["product_id"] for p in picks]
    data = None
    for _ in range(2):
        try:
            d = parse_json(chat([{"role": "user", "content": prompt}], model=coach_model(),
                                temperature=float(setting("COACH_TEMPERATURE", "0.2")), max_tokens=1200, json_mode=True))
        except AIError:
            continue
        if _valid_coach(d, missed, pick_ids):
            data = d
            break
    verdicts = {p.get("id"): p for p in (data or {}).get("picks", []) if isinstance(p, dict)}
    out_picks = []
    suitable = set(client.get("suitable_products", []))
    for pid in pick_ids:
        v = verdicts.get(pid, {})
        fits = pick_fits(pid, suitable, unsuitable, v.get("fits"))
        why = str(v.get("why") or "").strip()
        if not why or (pid in unsuitable and v.get("fits") is True):
            # The model's reason may argue the wrong way; use the client file's reason instead.
            why = unsuitable.get(pid) or ("It matches what the client needs." if fits else "It doesn't match what the client told you.")
        out_picks.append({"product_id": pid, "name": products[pid]["name"], "fits": fits, "why": why})
    better = (data or {}).get("better_questions", {}) or {}
    out_needs = [{
        "id": d["id"], "label": by_id[d["id"]]["label"], "found": d["found"], "quote": d["asked"],
        "fact": by_id[d["id"]]["fact"].strip(),
        "better_question": "" if d["found"] else str(better.get(d["id"]) or ""),
    } for d in needs]
    if data is None:
        # Never hand back feedback with empty sections. The interview stays open and the student can try again.
        raise AIError("The coach couldn't write the feedback this time")
    fallback = {k: [str(x) for x in data[k]][:3] for k in ("went_well", "missed", "improve")}
    return {"found": sum(d["found"] for d in needs), "total": len(needs), "needs": out_needs, "picks": out_picks, **fallback}
