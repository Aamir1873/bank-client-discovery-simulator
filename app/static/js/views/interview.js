// Step 2: the interview. Client file and notes on the left, the chat in the middle, the products on the right.
import { W } from '../words.js';
import {
  h, button, panelHead, avatar, factRow, quote, field, chipGroup, bubble, typing, errorLine, hintNote,
  productRow, groupedList, dialog, limitCounter,
} from '../ui.js';
import { api } from '../api.js';
import * as store from '../state.js';

export default async function interview({ root, actions, state, go }) {
  if (!state.interviewId || !state.client) return go('pick');
  const client = state.client;
  root.className = 'view wide';

  // ---- top actions: hint + end ----------------------------------------------------------------
  const hintBtn = button(W.interview.hint, { kind: 'out', icon: 'hint' });
  const hintLeft = h('span', { class: 'hint-left', 'aria-live': 'polite' });
  const endBtn = button(W.interview.end, { kind: 'go' });
  actions.append(hintBtn, hintLeft, endBtn);

  // ---- left: client file + notes ---------------------------------------------------------------
  const notes = field(W.interview.notes, {
    multiline: true, value: state.notes, hideLabel: true,
    onInput: (v) => store.set({ notes: v }),
  });
  notes.input.classList.add('textarea');
  const left = h('aside', { class: 'panel', 'aria-label': W.interview.file },
    panelHead(W.interview.file),
    h('div', { class: 'panel-body' },
      client.known.map((k) => factRow(k.label, k.value)),
      h('div', { style: 'margin-top:10px' }, h('h3', {}, W.interview.saidBooking), quote(client.opening_line))),
    h('div', { class: 'notes' },
      h('div', { class: 'panel-head', style: 'border:0;padding-bottom:4px' }, h('h2', {}, W.interview.notes)),
      h('p', { class: 'help' }, W.interview.notesHelp),
      notes.input));
  notes.input.setAttribute('aria-label', W.interview.notes);

  // ---- middle: chat ------------------------------------------------------------------------
  const messages = h('div', { class: 'messages', role: 'log', 'aria-label': client.name, 'aria-live': 'polite' });
  const box = h('textarea', { class: 'textarea', rows: '1', placeholder: W.interview.placeholder, 'aria-label': W.interview.placeholder, value: state.draft });
  const sendBtn = button(null, { kind: 'ink', icon: 'send', label: W.interview.send });
  const turnsLine = h('span', { style: 'font-variant-numeric:tabular-nums' });
  const boxCount = limitCounter(box, 1000);
  const chat = h('section', { class: 'chat', 'aria-label': client.name },
    h('div', { class: 'chat-head' }, avatar(client.name),
      h('div', {}, h('b', {}, client.name), h('span', {}, client.intro)),
      h('span', { class: 'sp' }),
      h('button', { class: 'link', type: 'button', onClick: () => showFile() }, W.interview.hisFile)),
    messages,
    h('div', { class: 'composer' },
      h('div', { class: 'line' }, box, sendBtn),
      h('div', { class: 'meta' }, turnsLine, boxCount, h('span', { class: 'enter' }, W.interview.enterHint))));

  // ---- right: products -----------------------------------------------------------------------
  const listEl = h('div', { class: 'catalogue' }, h('p', { class: 'loading' }, W.loading));
  const tools = h('div', { class: 'catalogue-tools' });
  const right = h('aside', { class: 'panel', 'aria-label': W.products.title },
    h('div', { class: 'panel-head' },
      h('div', { style: 'display:flex;align-items:baseline;justify-content:space-between' }, h('h2', {}, W.products.title)),
      h('p', {}, W.products.help(client.name)),
      tools),
    h('div', { class: 'panel-body' }, listEl));

  root.append(h('div', { class: 'interview' }, left, chat, right));

  // ---- chat drawing --------------------------------------------------------------------------
  // The log only ever grows: new items are appended, so screen readers announce just the new one.
  function itemEl(it) {
    if (it.kind === 'me') return bubble('me', W.interview.you, it.text);
    if (it.kind === 'client') return bubble('client', client.name, it.text);
    if (it.kind === 'hint') return hintNote(W.interview.hintFound(it.found, it.total), it.text);
    if (it.kind === 'error') return errorLine(it.text, it.retry ? () => retry(it.retry) : null);
    return null;
  }

  function drawAll() {
    const items = store.get().items;
    const els = items.map(itemEl).filter(Boolean);
    if (!items.length) els.push(h('p', { class: 'empty' }, W.interview.start(client.name)));
    messages.replaceChildren(...els);
    messages.scrollTop = messages.scrollHeight;
  }

  function push(it) {
    store.set({ items: [...store.get().items, it] });
    messages.querySelector(':scope > .empty')?.remove();
    messages.append(itemEl(it));
    messages.scrollTop = messages.scrollHeight;
  }

  function clearErrors() {
    store.set({ items: store.get().items.filter((it) => it.kind !== 'error') });
    messages.querySelectorAll(':scope > .error-line').forEach((el) => el.remove());
  }

  let pending = null;
  function showWaiting(label) {
    pending = typing(label);
    messages.append(pending);
    messages.scrollTop = messages.scrollHeight;
  }
  function hideWaiting() { pending?.remove(); pending = null; }

  function drawMeta() {
    const s = store.get();
    turnsLine.textContent = W.interview.turns(s.turns, s.maxTurns);
    const full = s.turns >= s.maxTurns;
    sendBtn.disabled = busy || full;
    box.disabled = full;
    box.placeholder = full ? W.interview.full : W.interview.placeholder;
    hintBtn.disabled = busy || s.hintsLeft <= 0;
    hintLeft.textContent = s.hintsUsed ? W.interview.hintsLeft(s.hintsLeft) : '';
  }

  /** What to do with a failed call. 404: the server restarted and the interview is gone. */
  function failed(e, action) {
    if (e.status === 404) {
      store.reset({ notice: W.errors.notFound });
      go('pick');
      return true;
    }
    // 400/409: the request itself was refused; repeating it won't help, so no Try again.
    const canRetry = !(e.status >= 400 && e.status < 500);
    push({ kind: 'error', text: e.message, retry: canRetry ? action : null });
    return false;
  }

  let busy = false;
  let lastText = '';

  async function send(text, { again = false } = {}) {
    if (busy || !text) return;
    busy = true;
    lastText = text;
    clearErrors();
    // Trying again sends the same question without showing it twice.
    if (!again) push({ kind: 'me', text });
    store.set({ draft: '' });
    box.value = '';
    box.dispatchEvent(new Event('input'));
    showWaiting(W.interview.replying(client.name));
    drawMeta();
    let left = false;
    try {
      const r = await api.send(store.get().interviewId, text);
      hideWaiting();
      store.set({ turns: r.turns, maxTurns: r.max_turns });
      push({ kind: 'client', text: r.reply });
    } catch (e) {
      hideWaiting();
      left = failed(e, 'send');
    } finally {
      busy = false;
      if (!left) { drawMeta(); box.focus(); }
    }
  }

  async function askHint() {
    if (busy) return;
    busy = true;
    clearErrors();
    showWaiting(W.interview.hinting);
    drawMeta();
    let left = false;
    try {
      const r = await api.hint(store.get().interviewId);
      hideWaiting();
      store.set({ hintsLeft: r.hints_left, hintsUsed: store.get().hintsUsed + 1 });
      push({ kind: 'hint', found: r.found, total: r.total, text: r.nudge });
    } catch (e) {
      hideWaiting();
      left = failed(e, 'hint');
    } finally {
      busy = false;
      if (!left) drawMeta();
    }
  }

  // Try again repeats the action that failed: a failed hint never re-sends a question.
  function retry(action) {
    if (action === 'hint') return askHint();
    return send(lastText || lastQuestion(), { again: true });
  }
  function lastQuestion() {
    const mine = store.get().items.filter((it) => it.kind === 'me');
    return mine.length ? mine[mine.length - 1].text : '';
  }

  sendBtn.addEventListener('click', () => send(box.value.trim()));
  box.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(box.value.trim()); }
  });
  box.addEventListener('input', () => store.set({ draft: box.value }));

  // ---- hint ----------------------------------------------------------------------------------
  hintBtn.addEventListener('click', askHint);

  // ---- end -----------------------------------------------------------------------------------
  endBtn.addEventListener('click', () => {
    dialog({
      title: W.interview.endTitle,
      body: W.interview.endBody,
      actions: (close) => [
        button(W.interview.keepTalking, { kind: 'out', onClick: close }),
        button(W.interview.toWrapup, { kind: 'go', onClick: () => { close(); go('wrapup'); } }),
      ],
    });
  });

  function showFile() {
    dialog({
      title: W.brief.title(client.name),
      body: client.intro,
      content: [client.known.map((k) => factRow(k.label, k.value)), h('h3', { style: 'margin-top:8px' }, W.brief.booked), quote(client.opening_line)],
      actions: (close) => [button(W.brief.back, { kind: 'out', onClick: close })],
    });
  }

  // ---- products --------------------------------------------------------------------------------
  let group = 'all';
  let kind = 'all';
  let term = '';
  let catalogue;
  const search = h('input', { class: 'input', type: 'search', placeholder: W.products.search, 'aria-label': W.products.search });
  search.addEventListener('input', () => { term = search.value.trim().toLowerCase(); drawProducts(); });

  function drawTools() {
    tools.replaceChildren(
      search,
      chipGroup([['all', W.products.all], ...catalogue.groups.map((g) => [g.id, g.name])], group,
        (v) => { group = v; redrawTools(); drawProducts(); }, { label: W.products.title }),
      chipGroup([['all', W.products.both], ['islamic', W.products.islamic], ['conventional', W.products.conventional]], kind,
        (v) => { kind = v; redrawTools(); drawProducts(); }, { label: `${W.products.islamic} / ${W.products.conventional}`, cls: 'seg' }));
  }

  // Redrawing the filters replaces their buttons, so put keyboard focus back on the one just pressed.
  function redrawTools() {
    const label = document.activeElement && tools.contains(document.activeElement) ? document.activeElement.textContent : null;
    drawTools();
    if (label) [...tools.querySelectorAll('button')].find((b) => b.textContent === label)?.focus();
  }

  function drawProducts() {
    const shown = catalogue.products.filter((p) =>
      (group === 'all' || p.group === group)
      && (kind === 'all' || p.type === kind)
      && (!term || `${p.name} ${p.features.join(' ')}`.toLowerCase().includes(term)));
    listEl.replaceChildren(...groupedList(catalogue.groups, shown, (p) => productRow(p, {
      action: button(W.products.describe(client.name), {
        kind: 'out', small: true,
        onClick: () => { box.value = W.products.describeText(p.name, p.features[0]); store.set({ draft: box.value }); box.focus(); },
      }),
    }), { emptyText: W.products.none }));
  }

  drawAll();
  drawMeta();
  try {
    catalogue = await api.catalogue();
    drawTools();
    drawProducts();
  } catch (e) {
    listEl.replaceChildren(errorLine(e.message));
  }
}
