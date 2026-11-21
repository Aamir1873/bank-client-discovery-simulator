// Step 1: pick a client. Who they are and why they came. Nothing about what they keep back.
import { W } from '../words.js';
import { h, card, avatar, quote, difficultyTag, button, empty, errorLine } from '../ui.js';
import { api } from '../api.js';
import * as store from '../state.js';

export default async function pick({ root, go }) {
  root.className = 'view';
  root.append(h('h1', {}, W.pick.title), h('p', { class: 'lede' }, W.pick.lede));
  const { notice } = store.get();
  if (notice) {
    root.append(h('p', { class: 'notice', role: 'status' }, notice));
    store.set({ notice: null });
  }
  const grid = h('div', { class: 'clients' }, h('p', { class: 'loading' }, W.loading));
  root.append(grid);

  let clients;
  try {
    clients = await api.clients();
  } catch (e) {
    grid.replaceChildren(errorLine(e.message, () => go('pick')));
    return;
  }
  if (!clients.length) {
    grid.replaceChildren(empty(W.pick.empty));
    return;
  }
  const chosen = store.get().clientId || clients[0].id;
  grid.replaceChildren(...clients.map((c) => card([
    h('div', { class: 'who' }, avatar(c.name), h('div', {}, h('b', {}, c.name), h('span', {}, c.intro))),
    quote(c.opening_line),
    difficultyTag(c.difficulty),
    button(W.pick.meet(c.name), {
      kind: c.id === chosen ? 'go' : 'out',
      onClick: () => store.reset() || go('brief', { clientId: c.id }),
    }),
  ], { cls: 'client-card', pad: false, selected: c.id === chosen })));
}
