"""Re-score a saved leak test report with one judge, without running the interviews again.

    python scripts/rescore.py leak-reports/<report>.md --judge gemma4:12b

Reads the transcripts in the report, runs the app's found check on each with the given judge, and writes
a new report next to it. Use it to compare client models fairly: same judge, same transcripts.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import ai, content  # noqa: E402
from app.llm import AIError  # noqa: E402


def parse(report: str) -> list[dict]:
    """Each '### client, run n, vague|trigger id' block becomes {cid, run, need, history}.
    Blocks the first judge failed on are judged again; older reports kept no transcript for those, so they are skipped."""
    blocks = []
    for blk in re.split(r"\n(?=### )", report):
        m = re.match(r"### (\S+), run (\d+), (?:trigger (\S+)|vague)\n", blk)
        if not m:
            continue
        cid, run, need = m.group(1), int(m.group(2)), m.group(3)
        name = content.load_client(cid)["name"]
        history = []
        for line in blk.splitlines()[1:]:
            if line.startswith("Banker: "):
                history.append({"role": "user", "content": line[len("Banker: "):]})
            elif line.startswith(name + ": "):
                history.append({"role": "assistant", "content": line[len(name) + 2:]})
            elif line.startswith("**"):
                break
        if history:
            blocks.append({"cid": cid, "run": run, "need": need, "history": history})
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--judge", required=True)
    args = ap.parse_args()
    os.environ["COACH_MODEL"] = args.judge
    src = Path(args.report)
    text = src.read_text(encoding="utf-8")
    client_model = re.search(r"^# Leak test: (.+)$", text, flags=re.M).group(1)
    cases = yaml.safe_load((content.ROOT / "tests" / "leak_cases.yaml").read_text())

    stats, log = {}, []
    for b in parse(text):
        client = content.load_client(b["cid"])
        s = stats.setdefault(b["cid"], {"early": 0, "extra": 0, "missed": 0, "failed": 0, "n": 0})
        try:
            found = ai.found_check(client, b["history"])
        except AIError:
            s["failed"] += 1
            continue
        if b["need"] is None:
            s["early"] += len(found)
            what = "vague"
        else:
            s["n"] += 1
            s["missed"] += b["need"] not in found
            s["extra"] += len([f for f in found if f != b["need"]])
            what = f"trigger {b['need']}"
        log.append(f"- {b['cid']}, run {b['run']}, {what}: {found or 'nothing'}")
        print(log[-1], flush=True)

    table = ["| Client | Leaked on vague questions | Leaked on another need's question | Did not come out when asked | Trigger questions | Judge failed |",
             "| --- | --- | --- | --- | --- | --- |"]
    table += [f"| {c} | {v['early']} | {v['extra']} | {v['missed']} | {v['n']} | {v['failed']} |" for c, v in stats.items() if c in cases]
    out = src.with_name(src.stem + f"-rescored-{args.judge.replace(':', '-')}.md")
    out.write_text(f"# Leak test: {client_model}, re-scored\n\nTranscripts from {src.name}. Judge: {args.judge}.\n\n"
                   + "\n".join(table) + "\n\n## What the judge found\n\n" + "\n".join(log) + "\n", encoding="utf-8")
    print("\n" + "\n".join(table) + f"\n\nReport: {out.relative_to(content.ROOT)}")


if __name__ == "__main__":
    try:
        content.validate_all()
        main()
    except (AIError, content.ContentError) as e:
        sys.exit(f"Stopped: {e}")
