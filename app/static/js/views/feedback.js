// Step 4: feedback. Found X of Y, one card per hidden need, each pick checked, the coach's three areas, export.
import { W } from '../words.js';
import { h, card, statusLabel, icon, button, errorLine } from '../ui.js';
import { api } from '../api.js';
import * as store from '../state.js';

export default async function feedback({ root, actions, state, go }) {
  const fb = state.feedback;
  if (!fb || !state.client) return go('pick');
  const client = state.client;
  root.className = 'view';

  // A plain link: the server sends the file as a download (no download attribute, so a redirect is followed).
  // After a server restart the server sends the browser back here with #export-ended, and this says why.
  actions.append(h('a', { class: 'bt out', href: api.exportUrl(state.interviewId) }, icon('download'), W.feedback.export));
  if (location.hash === '#export-ended') {
    history.replaceState(null, '', location.pathname + location.search);
    root.append(errorLine(W.feedback.exportEnded));
  }

  const needCard = (n) => card([
    statusLabel(n.found),
    h('b', {}, n.label),
    n.found
      ? (n.quote ? h('q', {}, n.quote) : null)
      : h('span', { style: 'color:var(--ink-2)' }, n.fact),
    !n.found && n.better_question
      ? h('div', { class: 'ask' }, h('span', {}, W.feedback.better), n.better_question)
      : null,
  ], { cls: `need${n.found ? '' : ' missed'}`, pad: false });

  const verdict = (p) => h('div', { class: `verdict ${p.fits ? 'ok' : 'no'}` },
    icon(p.fits ? 'ok' : 'no', 'ic-sm'), h('b', {}, p.name), h('span', {}, `${p.fits ? W.feedback.fits : W.feedback.notFit} ${p.why}`));

  const area = (title, colour, points) => card([
    h('h2', {}, h('span', { class: 'dot', style: `background:var(${colour})` }), title),
    h('ul', {}, (points || []).map((t) => h('li', {}, t))),
  ], { cls: 'area', pad: false });

  root.append(
    h('div', { class: 'fb-top' },
      h('div', {}, h('h1', {}, W.feedback.title(client.name)), h('p', { class: 'lede', style: 'margin-bottom:0' }, W.feedback.meta(fb.turns, fb.hints_used))),
      h('div', { class: 'found' }, h('span', { class: 'big' }, W.feedback.of(fb.found, fb.total)), h('span', { class: 'mute' }, W.feedback.found))),
    h('div', { class: 'needs' }, fb.needs.map(needCard)),
    h('div', { class: 'verdicts' }, fb.picks.map(verdict)),
    h('div', { class: 'areas' },
      area(W.feedback.wentWell, '--green', fb.went_well),
      area(W.feedback.missed, '--red', fb.missed),
      area(W.feedback.improve, '--amber', fb.improve)),
    h('div', { class: 'foot' },
      h('span', { class: 'mute' }, W.feedback.exportNote),
      h('div', { class: 'group' },
        button(W.feedback.another, { onClick: () => { store.reset(); go('pick'); } }),
        button(W.feedback.again(client.name), { kind: 'go', onClick: () => { const id = client.id; store.reset(); go('brief', { clientId: id }); } }))));
}
