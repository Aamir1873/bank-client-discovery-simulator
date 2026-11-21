// h() builds elements safely (text goes in as textContent, never as HTML).
// The components below are reused by every view.
import { W } from './words.js';

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') el.setAttribute('style', v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else if (k === 'open') el.open = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

// ---- icons (inline SVG, drawn from fixed paths, no outside text) -----------------------------
const PATHS = {
  send: 'M5 12h14M13 6l6 6-6 6',
  hint: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.6.6 1 1.4 1 2.3V16h6v-.2c0-.9.4-1.7 1-2.3A6 6 0 0 0 12 3z',
  info: 'M12 8v5M12 16h.01M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z',
  ok: 'M5 12l5 5 9-10',
  no: 'M6 6l12 12M18 6L6 18',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
};

export function icon(name, cls = 'ic') {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('class', cls);
  const p = document.createElementNS(ns, 'path');
  p.setAttribute('d', PATHS[name]);
  svg.append(p);
  return svg;
}

// ---- components --------------------------------------------------------------------------

/** kind: go (moves the flow forward) | ink (the screen's own action) | out (open, view, back) | no */
export function button(label, { kind = 'out', onClick, icon: ic, small, disabled, label: aria, type = 'button' } = {}) {
  return h('button', { class: `bt ${kind}${small ? ' sm' : ''}${!label ? ' icon' : ''}`, type, onClick, disabled, 'aria-label': aria },
    ic ? icon(ic) : null, label || null);
}

export function card(children, { cls = '', pad = true, selected = false } = {}) {
  return h('div', { class: `card${pad ? ' pad' : ''}${selected ? ' selected' : ''} ${cls}`.trim() }, children);
}

export function panelHead(title, help) {
  return h('div', { class: 'panel-head' }, h('h2', {}, title), help ? h('p', {}, help) : null);
}

export function avatar(name) {
  const letters = name.split(/\s+/).filter((w) => w && w.toLowerCase() !== 'and').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  return h('span', { class: 'avatar', 'aria-hidden': 'true' }, letters);
}

export function figure(label, value) {
  return h('div', { class: 'figure' }, h('span', {}, label), h('b', {}, value));
}

export function factRow(label, value) {
  return h('div', { class: 'row' }, h('span', {}, label), h('b', {}, value));
}

export function quote(text) {
  return h('p', { class: 'quote' }, `“${text}”`);
}

export function difficultyTag(level) {
  return h('span', { class: `tag ${level}` }, W.pick.difficulty[level] || level);
}

export function kindTag(type) {
  return h('span', { class: `kind ${type}` }, type === 'islamic' ? W.products.islamic : W.products.conventional);
}

let fieldCount = 0;
/** A labelled text field. multiline → textarea. Returns { el, input }. */
export function field(label, { value = '', multiline = false, rows = 4, help, placeholder, onInput, hideLabel = false, maxlength } = {}) {
  const id = `f${++fieldCount}`;
  const input = multiline
    ? h('textarea', { id, class: 'textarea', rows, placeholder, value })
    : h('input', { id, class: 'input', type: 'text', placeholder, value });
  if (onInput) input.addEventListener('input', (e) => onInput(e.target.value));
  const count = maxlength ? limitCounter(input, maxlength) : null;
  const el = h('div', { class: 'field' },
    h('label', { for: id, class: hideLabel ? 'sr' : null }, label),
    help ? h('span', { class: 'help' }, help) : null,
    input, count);
  return { el, input };
}

/** Caps a field and shows "n of max characters" only when within 100 of the limit. */
export function limitCounter(input, max) {
  input.maxLength = max;
  const el = h('span', { class: 'counter', 'aria-live': 'polite' });
  const update = () => {
    const n = input.value.length;
    el.textContent = n >= max - 100 ? W.chars(n, max) : '';
  };
  input.addEventListener('input', update);
  update();
  return el;
}

/** Toggle buttons that share one pressed value. */
export function chipGroup(options, value, onPick, { label, cls = 'chips' } = {}) {
  const wrap = h('div', { class: cls, role: 'group', 'aria-label': label });
  for (const [id, text] of options) {
    wrap.append(h('button', {
      type: 'button',
      class: cls === 'chips' ? 'chip' : null,
      'aria-pressed': String(id === value),
      onClick: () => onPick(id),
    }, text));
  }
  return wrap;
}

export function bubble(kind, who, text) {
  return h('div', { class: `bubble ${kind}` }, h('small', {}, who), text);
}

export function typing(label) {
  return h('div', { class: 'typing', role: 'status', 'aria-label': label }, h('i'), h('i'), h('i'));
}

export function errorLine(message, onRetry) {
  return h('div', { class: 'error-line', role: 'alert' },
    h('span', {}, message), onRetry ? button(W.interview.retry, { kind: 'out', small: true, onClick: onRetry }) : null);
}

export function hintNote(title, text) {
  return h('div', { class: 'note-hint', role: 'status' }, icon('hint'), h('div', {}, h('b', {}, title), h('div', {}, text)));
}

export function empty(text) {
  return h('p', { class: 'empty' }, text);
}

/** One product as an expandable row: name, one line, type; open for limits and an action. */
export function productRow(p, { action } = {}) {
  return h('details', { class: 'product' },
    h('summary', {},
      h('span', { class: 'pn' }, h('b', {}, p.name), h('small', {}, p.features.join('. '))),
      kindTag(p.type)),
    h('div', { class: 'pb' },
      h('span', { class: 'limits' }, h('b', {}, W.products.limits), ' ', p.limitations.join('. ')),
      action ? h('div', {}, action) : null));
}

/** A product as a checkbox option (wrap-up). */
export function productOption(p, checked, onToggle) {
  const input = h('input', { type: 'checkbox', checked, onChange: (e) => onToggle(e.target.checked) });
  return h('label', { class: 'option' }, input,
    h('span', {}, h('b', {}, p.name), h('small', {}, p.features[0])), kindTag(p.type));
}

/** Products grouped under their group names. render(p) draws one product. */
export function groupedList(groups, products, render, { emptyText } = {}) {
  const out = [];
  for (const g of groups) {
    const list = products.filter((p) => p.group === g.id);
    if (!list.length) continue;
    out.push(h('h3', { class: 'group-title' }, g.name, ' ', h('span', { class: 'num' }, String(list.length))));
    list.forEach((p) => out.push(render(p)));
  }
  if (!out.length && emptyText) out.push(empty(emptyText));
  return out;
}

/** A modal dialog. Returns a close() function. Esc and the first button close it; focus returns afterwards. */
export function dialog({ title, body, content, actions }) {
  const layer = document.getElementById('layer');
  const app = document.querySelector('.app');
  const back = document.activeElement;
  const titleId = `d${++fieldCount}`;
  const close = () => {
    box.remove();
    document.removeEventListener('keydown', onKey);
    if (app) app.inert = false;
    if (back && back.focus) back.focus();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key !== 'Tab') return;
    // Keep Tab inside the dialog.
    const items = [...box.querySelectorAll('button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])')].filter((el) => !el.disabled);
    if (!items.length) { e.preventDefault(); return; }
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && (document.activeElement === first || !box.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  const box = h('div', { class: 'dim' },
    h('div', { class: 'dialog', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId, tabindex: '-1' },
      h('div', { class: 'dialog-head' }, h('h2', { id: titleId }, title), body ? h('p', {}, body) : null),
      content ? h('div', { class: 'dialog-body' }, content) : null,
      h('div', { class: 'dialog-foot' }, actions(close))));
  box.addEventListener('click', (e) => { if (e.target === box) close(); });
  document.addEventListener('keydown', onKey);
  if (app) app.inert = true;
  layer.append(box);
  box.querySelector('.dialog').focus();
  return close;
}

export function statusLabel(ok) {
  return h('span', { class: `status ${ok ? 'ok' : 'no'}` }, icon(ok ? 'ok' : 'no', 'ic-sm'), ok ? W.feedback.foundLabel : W.feedback.missedLabel);
}
