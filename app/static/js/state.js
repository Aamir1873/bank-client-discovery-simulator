// One small store for the whole flow. Saved to sessionStorage so a reload keeps the interview.
const KEY = 'discovery-state-v1';

const blank = () => ({
  view: 'pick',
  clientId: null,
  client: null,        // public client from the server
  interviewId: null,
  maxTurns: 30,
  turns: 0,
  hintsLeft: 2,
  hintsUsed: 0,
  items: [],           // chat: {kind:'me'|'client'|'hint'|'error', text, found?, total?}
  draft: '',
  notes: '',
  summary: null,       // null until the wrap-up opens, then the student's text
  picks: {},           // product_id -> reason
  feedback: null,
  notice: null,        // a message shown once on the pick screen
});

function load() {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? { ...blank(), ...JSON.parse(raw) } : blank();
  } catch {
    return blank();
  }
}

let state = load();
const listeners = new Set();

export function get() {
  return state;
}

export function set(patch) {
  state = { ...state, ...patch };
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode: keep it in memory */ }
  listeners.forEach((fn) => fn(state));
}

export function reset(patch = {}) {
  state = blank();
  set(patch);
}

export function onChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
