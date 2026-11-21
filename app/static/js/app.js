// Router: one view at a time, chosen by state.view. The step bar and top actions follow it.
import { W } from './words.js';
import { h, clear, dialog, button } from './ui.js';
import * as store from './state.js';
import pick from './views/pick.js';
import brief from './views/brief.js';
import interview from './views/interview.js';
import wrapup from './views/wrapup.js';
import feedback from './views/feedback.js';

const VIEWS = { pick, brief, interview, wrapup, feedback };
const STEP = { pick: 0, brief: 0, interview: 1, wrapup: 2, feedback: 3 };

const main = document.getElementById('view');
const steps = document.getElementById('steps');
const actions = document.getElementById('top-actions');
let current = null;

export function go(view, patch = {}) {
  store.set({ ...patch, view });
  render();
}

function drawSteps(view) {
  clear(steps);
  const on = STEP[view] ?? 0;
  W.steps.forEach((label, i) => {
    steps.append(h('span', { class: `step${i === on ? ' on' : ''}${i < on ? ' done' : ''}`, 'aria-current': i === on ? 'step' : null },
      h('i', {}, String(i + 1)), h('span', {}, label)));
  });
}

async function render() {
  const s = store.get();
  const name = VIEWS[s.view] ? s.view : 'pick';
  if (current && current.destroy) current.destroy();
  drawSteps(name);
  clear(actions);
  clear(main);
  main.className = '';
  current = await VIEWS[name]({ root: main, actions, state: s, go });
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

document.getElementById('brand').addEventListener('click', (e) => {
  e.preventDefault();
  const s = store.get();
  const leave = () => { store.reset(); render(); };
  // An interview in progress is lost on leaving, so ask first.
  if (!s.interviewId || !['interview', 'wrapup'].includes(s.view)) return leave();
  dialog({
    title: W.interview.leaveTitle,
    body: W.interview.leaveBody,
    actions: (close) => [
      button(W.interview.stay, { kind: 'out', onClick: close }),
      button(W.interview.leave, { kind: 'no', onClick: () => { close(); leave(); } }),
    ],
  });
});

render();
