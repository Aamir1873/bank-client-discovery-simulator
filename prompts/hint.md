<!--
The hint's nudge. Sent when the student taps "Ask for a hint" (at most 2 per interview).
It gets only the client's name and the topic of one need that is still hidden, never the fact itself,
so it cannot give the answer away. The count shown with it comes from the found check, not from here.
The reply must be JSON only.
-->
A trainee banker is interviewing a customer called {{name}}. There is an area they have not asked about yet. It is described here only as a topic:

{{topic}}

Write one short nudge that points the trainee towards this area, as a direction to explore.

Rules:
- One sentence, plain words, second person. Example: "You haven't asked what he already owes."
- Don't write a question for them to copy, and don't guess any facts or numbers.

Reply with JSON only, no other text:

{"nudge": "<one sentence>"}
