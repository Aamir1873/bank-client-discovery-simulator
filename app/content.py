"""Load the editable content (clients, products, prompts) and turn it into prompt text.

Everything is read from disk on each call, so edits to content/ and prompts/ show up without a restart.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
PROMPTS = ROOT / "prompts"

PROFILE_KEYS = ("id", "name", "intro", "difficulty", "opening_line", "persona", "background", "known", "stated_needs")
NEED_KEYS = ("id", "label", "fact", "reveal_when", "keywords", "while_closed", "importance")
PRODUCT_KEYS = ("id", "name", "group", "type", "features", "limitations")


class ContentError(Exception):
    """A content file is missing, broken or refers to something that doesn't exist."""


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContentError(f"{path.relative_to(ROOT)} is missing")
    except yaml.YAMLError as e:
        # The parser's message quotes the broken line, which can be a hidden fact. Log it on the server only.
        logging.getLogger("uvicorn.error").error("%s is not valid YAML: %s", path.relative_to(ROOT), e)
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark else ""
        raise ContentError(f"{path.relative_to(ROOT)} is not valid YAML{where}. See the server log for details.")
    if not isinstance(data, dict):
        raise ContentError(f"{path.relative_to(ROOT)} should be a YAML mapping")
    return data


def _need_keys(path: Path, item: dict, keys: tuple, what: str) -> None:
    missing = [k for k in keys if k not in item]
    if missing:
        raise ContentError(f"{path.relative_to(ROOT)}: {what} {item.get('id', '?')} is missing {', '.join(missing)}")


def load_catalogue() -> dict:
    path = CONTENT / "products.yaml"
    data = _read_yaml(path)
    groups = {g["id"]: g["name"] for g in data.get("groups", [])}
    seen = set()
    for p in data.get("products", []):
        _need_keys(path, p, PRODUCT_KEYS, "product")
        if p["group"] not in groups:
            raise ContentError(f"{path.relative_to(ROOT)}: product {p['id']} has unknown group {p['group']}")
        if p["type"] not in ("islamic", "conventional"):
            raise ContentError(f"{path.relative_to(ROOT)}: product {p['id']} type must be islamic or conventional")
        if p["id"] in seen:
            raise ContentError(f"{path.relative_to(ROOT)}: product id {p['id']} is used twice")
        seen.add(p["id"])
    return {"groups": data["groups"], "products": data["products"]}


def client_ids() -> list[str]:
    return sorted(d.name for d in (CONTENT / "clients").iterdir() if (d / "profile.yaml").exists())


def load_client(client_id: str) -> dict:
    """The full client: profile plus hidden needs. Server side only."""
    if client_id not in client_ids():
        raise ContentError(f"Unknown client: {client_id}")
    folder = CONTENT / "clients" / client_id
    profile = _read_yaml(folder / "profile.yaml")
    hidden = _read_yaml(folder / "hidden.yaml")
    pfile, hfile = folder / "profile.yaml", folder / "hidden.yaml"
    _need_keys(pfile, profile, PROFILE_KEYS, "client")
    if profile["id"] != client_id:
        raise ContentError(f"{pfile.relative_to(ROOT)}: id is {profile['id']!r} but the folder is {client_id!r}; make them the same")
    if profile["difficulty"] not in ("easy", "medium", "hard"):
        raise ContentError(f"{pfile.relative_to(ROOT)}: difficulty must be easy, medium or hard")
    for key in ("known", "stated_needs"):
        if not isinstance(profile[key], list):
            raise ContentError(f"{pfile.relative_to(ROOT)}: {key} must be a list")
    needs = hidden.get("hidden_needs")
    if not isinstance(needs, list) or not needs:
        raise ContentError(f"{hfile.relative_to(ROOT)}: hidden_needs must be a list with at least one need")
    seen = set()
    for n in needs:
        if not isinstance(n, dict):
            raise ContentError(f"{hfile.relative_to(ROOT)}: each hidden need must be a mapping with id, label, fact and so on")
        _need_keys(hfile, n, NEED_KEYS, "hidden need")
        if n["id"] in seen:
            raise ContentError(f"{hfile.relative_to(ROOT)}: hidden need id {n['id']} is used twice")
        seen.add(n["id"])
        if not isinstance(n["keywords"], list):
            raise ContentError(f"{hfile.relative_to(ROOT)}: keywords for {n['id']} must be a list, like [paid, invoice]")
        if n["importance"] not in ("critical", "moderate"):
            raise ContentError(f"{hfile.relative_to(ROOT)}: importance for {n['id']} must be critical or moderate")
    for key in ("suitable_products", "unsuitable_products"):
        if not isinstance(hidden.get(key, []), list):
            raise ContentError(f"{hfile.relative_to(ROOT)}: {key} must be a list")
    product_ids = {p["id"] for p in load_catalogue()["products"]}
    refs = list(hidden.get("suitable_products", [])) + [u["id"] for u in hidden.get("unsuitable_products", [])]
    unknown = [r for r in refs if r not in product_ids]
    if unknown:
        raise ContentError(f"{(folder / 'hidden.yaml').relative_to(ROOT)} refers to unknown products: {', '.join(unknown)}")
    return {**profile, **hidden}


def public_client(client: dict) -> dict:
    """What the browser may see before the feedback. No hidden needs, no product verdicts."""
    return {k: client[k] for k in ("id", "name", "intro", "difficulty", "opening_line", "background", "known", "stated_needs")}


def validate_all() -> None:
    """Load everything once; raises ContentError naming the broken file."""
    load_catalogue()
    for cid in client_ids():
        load_client(cid)
    for name in ("client", "gate", "judge", "hint", "coach"):
        if not (PROMPTS / f"{name}.md").exists():
            raise ContentError(f"prompts/{name}.md is missing")


# ---- prompt text -------------------------------------------------------------------------------

def render(template: str, **values: str) -> str:
    text = re.sub(r"<!--.*?-->\s*", "", (PROMPTS / f"{template}.md").read_text(encoding="utf-8"), flags=re.S)
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)) - set(values))
    if missing:
        raise ContentError(f"prompts/{template}.md needs values for: {', '.join(missing)}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values[m.group(1)]), text).strip()


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items)


def known_text(client: dict) -> str:
    return _bullets(f"{k['label']}: {k['value']}" for k in client["known"])


def needs_for_judge(client: dict) -> str:
    return "\n".join(f"- id: {n['id']}\n  what it is: {n['fact'].strip()}" for n in client["hidden_needs"])


def needs_by_id(client: dict) -> dict:
    return {n["id"]: n for n in client["hidden_needs"]}


def client_system_prompt(client: dict, opened: list[str], answer_now: str | None = None) -> str:
    """The client only ever sees the needs already opened. Closed ones appear as their general line only,
    with no fact in them, so a small model cannot leak what it was never told."""
    needs = needs_by_id(client)
    open_list = [needs[i] for i in opened if i in needs]
    closed = [n for n in client["hidden_needs"] if n["id"] not in opened]
    open_text = "\n".join(f"- {n['fact'].strip()}" for n in open_list) or "- Nothing beyond why you came in."
    # Only the neutral line, never the label or topic: a label like "Supplier debt" would give the secret away.
    closed_text = "\n".join(f"- {n['while_closed']}" for n in closed) or "- None."
    now = ""
    if answer_now and answer_now in needs:
        now = ("\n## Answer this now\nThe banker has just asked about this. Tell them plainly and honestly, "
               f"in your own words, with any numbers:\n- {needs[answer_now]['fact'].strip()}\n")
    return render(
        "client",
        name=client["name"],
        persona=client["persona"].strip(),
        background=client["background"].strip(),
        known=known_text(client),
        stated_needs=_bullets(client["stated_needs"]),
        open_needs=open_text,
        closed_lines=closed_text,
        answer_now=now,
    )


def gate_prompt(client: dict, opened: list[str], history: list[dict]) -> str | None:
    closed = [n for n in client["hidden_needs"] if n["id"] not in opened]
    if not closed:
        return None
    message = history[-1]["content"] if history else ""
    before = history[-2]["content"] if len(history) >= 2 and history[-2]["role"] == "assistant" else "(this is the first message)"
    # Strip the block markers from the student's text so it can't close the quoted block early.
    message = message.replace("<<<", "").replace(">>>", "")
    return render(
        "gate",
        closed_needs="\n".join(f"- {n['id']}: {n['reveal_when']}" for n in closed),
        client_before=before,
        banker_message=message,
    )


def transcript_text(history: list[dict], client_name: str) -> str:
    who = {"user": "Banker", "assistant": client_name}
    return "\n".join(f"{who.get(m['role'], m['role'])}: {m['content']}" for m in history)


def products_text(catalogue: dict) -> str:
    out = []
    for p in catalogue["products"]:
        out.append(f"- {p['id']} | {p['name']} | {p['type']}\n  features: {'; '.join(p['features'])}\n  limitations: {'; '.join(p['limitations'])}")
    return "\n".join(out)
