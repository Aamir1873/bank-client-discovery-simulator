// Step 3: wrap-up. The summary (started from the notes), the products the student would offer, and why.
import { W } from '../words.js';
import { h, card, field, productOption, groupedList, button, errorLine, empty } from '../ui.js';
import { api } from '../api.js';
import * as store from '../state.js';

export default async function wrapup({ root, state, go }) {
  if (!state.interviewId || !state.client) return go('pick');
  const client = state.client;
  root.className = 'view';
  if (state.summary === null) store.set({ summary: state.notes.trim() });

  root.append(h('h1', {}, W.wrapup.title(client.name)), h('p', { class: 'lede' }, W.wrapup.lede));

  const summary = field(W.wrapup.summary, {
    multiline: true, rows: 6, value: store.get().summary, help: W.wrapup.summaryHelp, maxlength: 3000,
    onInput: (v) => store.set({ summary: v }),
  });
  const noteChips = state.notes.split('\n').map((l) => l.trim()).filter(Boolean).slice(0, 6);
  const reasons = h('div', { class: 'reasons' });
  const picksList = h('div', { class: 'picks-list' }, h('p', { class: 'loading' }, W.loading));
  const err = h('div');
  const submit = button(W.wrapup.submit, { kind: 'go' });

  root.append(h('div', { class: 'wrapup' },
    h('div', { class: 'stack' },
      card([summary.el, noteChips.length ? h('div', { class: 'from-notes', style: 'margin-top:8px' },
        h('span', {}, W.wrapup.fromNotes), noteChips.map((n) => h('span', {}, n))) : null]),
      card([h('h2', {}, W.wrapup.reasons), h('p', { class: 'mute', style: 'margin:2px 0 10px' }, W.wrapup.reasonsHelp), reasons])),
    card([h('h2', {}, W.wrapup.picks), h('p', { class: 'mute', style: 'margin:2px 0 10px' }, W.wrapup.picksHelp), picksList])),
  err,
  h('div', { class: 'foot' }, button(W.wrapup.back, { onClick: () => go('interview') }), submit));

  let catalogue;
  try {
    catalogue = await api.catalogue();
  } catch (e) {
    picksList.replaceChildren(errorLine(e.message));
    return;
  }
  const byId = Object.fromEntries(catalogue.products.map((p) => [p.id, p]));

  function drawPicks() {
    const picks = store.get().picks;
    picksList.replaceChildren(...groupedList(catalogue.groups, catalogue.products, (p) =>
      productOption(p, p.id in picks, (on) => {
        const next = { ...store.get().picks };
        if (on) next[p.id] = next[p.id] || ''; else delete next[p.id];
        store.set({ picks: next });
        drawReasons();
      })));
  }

  function drawReasons() {
    const picks = store.get().picks;
    const ids = Object.keys(picks).filter((id) => byId[id]);
    if (!ids.length) return reasons.replaceChildren(empty(W.wrapup.noPicks));
    reasons.replaceChildren(...ids.map((id) => {
      const p = byId[id];
      const f = field(W.wrapup.reasonFor(p.name), {
        value: picks[id],
        maxlength: 500,
        onInput: (v) => store.set({ picks: { ...store.get().picks, [id]: v } }),
      });
      f.el.append(h('span', { class: 'help limits' }, h('b', {}, W.products.limits), ' ', p.limitations.join('. ')));
      return f.el;
    }));
  }

  submit.addEventListener('click', async () => {
    const s = store.get();
    const text = (s.summary || '').trim();
    const picks = Object.entries(s.picks).map(([product_id, reason]) => ({ product_id, reason: reason.trim() }));
    if (!text) return err.replaceChildren(errorLine(W.wrapup.needSummary));
    if (!picks.length) return err.replaceChildren(errorLine(W.wrapup.needPick));
    submit.disabled = true;
    err.replaceChildren(h('p', { class: 'loading', role: 'status' }, W.wrapup.thinking));
    try {
      const fb = await api.feedback(s.interviewId, text, picks);
      go('feedback', { feedback: fb });
    } catch (e) {
      // 404: the server restarted and the interview is gone. Start again from the pick screen.
      if (e.status === 404) { store.reset({ notice: W.errors.notFound }); return go('pick'); }
      // 400/409: the input or the moment is wrong; trying the same thing again won't help.
      const canRetry = !(e.status >= 400 && e.status < 500);
      err.replaceChildren(errorLine(e.message, canRetry ? () => submit.click() : null));
      submit.disabled = false;
    }
  });

  drawPicks();
  drawReasons();
}
