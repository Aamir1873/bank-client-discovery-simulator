// Step 1b: before you meet. What the bank already has on file; the same facts stay visible in the interview.
import { W } from '../words.js';
import { h, card, figure, quote, button, icon, errorLine } from '../ui.js';
import { api } from '../api.js';
import * as store from '../state.js';

export default async function brief({ root, go, state }) {
  root.className = 'view';
  if (!state.clientId) return go('pick');
  const box = h('div', { class: 'brief' }, h('p', { class: 'loading' }, W.loading));
  root.append(box);

  let client;
  try {
    client = await api.client(state.clientId);
  } catch (e) {
    box.replaceChildren(errorLine(e.message, () => go('brief')));
    return;
  }

  const startBtn = button(W.brief.start, { kind: 'go' });
  const err = h('div');
  startBtn.addEventListener('click', async () => {
    startBtn.disabled = true;
    try {
      const r = await api.startInterview(client.id);
      go('interview', {
        interviewId: r.interview_id, client: r.client, maxTurns: r.max_turns, hintsLeft: r.hints_left,
        turns: 0, hintsUsed: 0, items: [], draft: '', notes: '', summary: null, picks: {}, feedback: null,
      });
    } catch (e) {
      err.replaceChildren(errorLine(e.message));
      startBtn.disabled = false;
    }
  });

  box.replaceChildren(card([
    h('div', { class: 'dialog-head', style: 'padding:0 0 10px' }, h('h1', {}, W.brief.title(client.name)), h('p', {}, client.intro)),
    h('div', { class: 'figures' }, client.known.map((k) => figure(k.label, k.value))),
    h('div', { style: 'margin-top:14px' }, h('h3', {}, W.brief.booked), quote(client.opening_line)),
    h('p', { class: 'hintline', style: 'margin-top:12px' }, icon('info'), W.brief.warn),
    err,
    h('div', { class: 'foot' }, button(W.brief.back, { onClick: () => go('pick') }), startBtn),
  ]));
  store.set({ client });
}
