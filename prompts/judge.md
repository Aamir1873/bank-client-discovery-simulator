<!--
The found check, one hidden need at a time. Used by the leak test and scripts/rescore.py (the app counts what
the gate opened). It sees only the customer's own lines, numbered; the code checks that the quote is in the
line it names. The reply must be one JSON object: some models (qwen4-max) otherwise list every line.
-->
Here is everything a bank customer said in a meeting, one line per turn:
{{lines}}

Hidden fact about the customer: {{label}}. {{fact}}

Does any line state this specific fact? It counts if the core of it is there, even without every detail.
It does not count if a line is only about a related or nearby topic. For example, saving money is not the same as sending money home, and owing suppliers is not the same as customers paying late. If unsure, answer 0.

Pick the one line that states it best, or 0. Reply with a single JSON object (not a list), no other text:

{"line": <the line number, or 0 if no line says it>, "quote": "<the words from that line that say it>"}
