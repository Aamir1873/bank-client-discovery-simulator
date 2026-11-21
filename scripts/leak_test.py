"""Leak test: does the AI Client keep its hidden needs until the right question?

    python scripts/leak_test.py --model gemma4:12b --runs 3
    python scripts/leak_test.py --model gemma4:12b --set reworded --runs 1

For each client and run:
  1. Vague questions in one conversation: no hidden need may come out.
  2. Each trigger question in a fresh conversation: its own need should come out, and no other.
The "what came out" judgement is the judge (prompts/judge.md), run on COACH_MODEL if set.
Writes a Markdown report to leak-reports/ (git-ignored).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import ai, content  # noqa: E402
from app.llm import AIError, coach_model  # noqa: E402


def check(client: dict, history: list[dict]) -> list[str] | None:
    """The app's found check. None when the judge could not answer, so one bad reply doesn't stop the run."""
    try:
        return ai.found_check(client, history)
    except AIError:
        return None


GATE_LOG: list = []  # what the gate opened on each turn, for the report


def ask(client: dict, state: tuple, question: str) -> tuple:
    """state = (history, opened). Runs the app's own turn: gate, then the client reply."""
    history, opened = state
    history = history + [{"role": "user", "content": question}]
    reply, opened, new = ai.turn(client, history, opened)
    GATE_LOG.append(new)
    return history + [{"role": "assistant", "content": reply}], opened


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="client model (defaults to AI_MODEL)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--clients", nargs="*", help="client ids (default: all)")
    ap.add_argument("--set", choices=["tuned", "reworded"], default="tuned",
                    help="tuned: one question per need (the ones the content was tuned on); reworded: the audit's 5 per need")
    args = ap.parse_args()
    if args.model:
        os.environ["AI_MODEL"] = args.model
    model = os.environ.get("AI_MODEL", "")
    cases = yaml.safe_load((content.ROOT / "tests" / "leak_cases.yaml").read_text())
    clients = args.clients or [c for c in cases if c != "reworded"]

    rows, log, t0 = [], [], time.time()
    for cid in clients:
        client = content.load_client(cid)
        case = cases[cid]
        early = missed = extra = failed = 0
        for run in range(1, args.runs + 1):
            # 1. vague questions: nothing should come out
            st = ([], [])
            for q in case["vague"]:
                st = ask(client, st, q)
            h = st[0]
            found = check(client, h)
            if found is None:
                failed += 1
                found = []
            early += len(found)
            log.append(f"### {cid}, run {run}, vague\n" + content.transcript_text(h, client["name"]) + f"\n\n**Came out:** {found or 'nothing'}\n")
            # 2. each trigger in a fresh conversation
            pairs = ([(nid, q) for nid, qs in cases["reworded"][cid].items() for q in qs] if args.set == "reworded"
                     else list(case["triggers"].items()))
            for need_id, q in pairs:
                h = ask(client, ask(client, ([], []), case["vague"][0]), q)[0]
                found = check(client, h)
                if found is None:
                    failed += 1
                    # keep the transcript so scripts/rescore.py can judge it again later
                    log.append(f"### {cid}, run {run}, trigger {need_id}\n" + content.transcript_text(h, client["name"])
                               + f"\n\n**Gate opened:** {GATE_LOG[-1] or 'nothing'}  **Came out:** judge gave no usable answer (not counted)\n")
                    continue
                if need_id not in found:
                    missed += 1
                others = [f for f in found if f != need_id]
                extra += len(others)
                log.append(f"### {cid}, run {run}, trigger {need_id}\n" + content.transcript_text(h, client["name"])
                           + f"\n\n**Gate opened:** {GATE_LOG[-1] or 'nothing'}  **Came out:** {found or 'nothing'}" + (f"  **Leaked:** {others}" if others else "") + "\n")
            print(f"{cid} run {run} done", flush=True)
        n = (sum(len(v) for v in cases["reworded"][cid].values()) if args.set == "reworded" else len(case["triggers"])) * args.runs
        rows.append((cid, early, extra, missed, n, failed))

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H%M")
    table = ["| Client | Leaked on vague questions | Leaked on another need's question | Did not come out when asked | Trigger questions | Judge failed |",
             "| --- | --- | --- | --- | --- | --- |"]
    table += [f"| {c} | {e} | {x} | {m} | {n} | {f} |" for c, e, x, m, n, f in rows]
    head = (f"# Leak test: {model}\n\n{stamp}. Runs per client: {args.runs}. Judge: {coach_model()}. "
            f"Took {int(time.time() - t0)} s.\n\nA leak is a hidden need said before the matching question. Lower is better.\n\n")
    out = content.ROOT / "leak-reports"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{stamp.replace(' ', '-')}-{model.replace(':', '-').replace('/', '-')}{'-reworded' if args.set == 'reworded' else ''}.md"
    path.write_text(head + "\n".join(table) + "\n\n## Transcripts\n\n" + "\n".join(log), encoding="utf-8")
    print("\n" + "\n".join(table) + f"\n\nReport: {path.relative_to(content.ROOT)}")


if __name__ == "__main__":
    try:
        content.validate_all()
        main()
    except (AIError, content.ContentError) as e:
        sys.exit(f"Stopped: {e}")
