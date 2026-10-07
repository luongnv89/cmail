'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { KEY, IDS, parse, init } = require('../docs/assets/checklist.js');

function fixture(storage = memory()) {
  const nodes = new Map();
  function node() {
    return { checked: false, hidden: true, textContent: '', listeners: {},
      addEventListener(type, callback) { this.listeners[type] = callback; },
      fire(type) { this.listeners[type](); } };
  }
  for (const id of IDS) nodes.set('#step-' + id, node());
  for (const id of ['progress-panel', 'setup-progress', 'progress-count', 'storage-notice', 'reset-progress']) nodes.set('#' + id, node());
  const root = { querySelector: id => nodes.get(id) };
  init(root, typeof storage === 'function' ? storage : () => storage);
  return { nodes, root, storage, first: nodes.get('#step-' + IDS[0]),
    count: nodes.get('#progress-count'), meter: nodes.get('#setup-progress'),
    notice: nodes.get('#storage-notice'), reset: nodes.get('#reset-progress') };
}
function memory() {
  const items = new Map();
  return { items, getItem: key => items.get(key) ?? null,
    setItem: (key, value) => items.set(key, value), removeItem: key => items.delete(key) };
}

test('missing progress has a clean baseline', () => {
  assert.deepEqual(parse(null), { steps: {}, corrupt: false });
});
test('valid versioned allowlisted booleans load', () => {
  assert.deepEqual(parse(JSON.stringify({ version: 1, steps: { readiness: true, install: false } })).steps,
    { readiness: true, install: false });
});
test('malformed/non-object/wrong-version/nonboolean/unknown state is rejected', () => {
  for (const raw of ['{', '', 'null', '42', 'true', '[]', '"text"', '{}',
    '{"version":2,"steps":{}}', '{"version":1,"steps":[]}',
    '{"version":1,"steps":{"readiness":"true"}}',
    '{"version":1,"steps":{"readiness":1}}',
    '{"version":1,"steps":{"token":"example-private-value"}}',
    '{"version":1,"steps":{"__proto__":true}}',
    '{"version":1,"steps":{},"domain":"example.com"}']) {
    assert.deepEqual(parse(raw), { steps: {}, corrupt: true }, raw);
  }
});
test('toggle/check/uncheck updates count and progress', () => {
  const f = fixture();
  assert.equal(f.meter.max, 14);
  assert.equal(f.meter.value, 0);
  assert.equal(f.nodes.get('#progress-panel').hidden, false);
  f.first.checked = true; f.first.fire('change');
  assert.equal(f.meter.value, 1);
  assert.match(f.count.textContent, /1 of 14/);
  f.first.checked = false; f.first.fire('change');
  assert.equal(f.meter.value, 0);
});
test('reload restores only boolean step progress', () => {
  const storage = memory(); const f = fixture(storage);
  f.first.checked = true; f.first.fire('change');
  assert.equal(fixture(storage).first.checked, true);
  const payload = JSON.parse(storage.items.get(KEY));
  assert.deepEqual(Object.keys(payload), ['version', 'steps']);
  assert.deepEqual(Object.keys(payload.steps), IDS);
  assert.ok(Object.values(payload.steps).every(value => typeof value === 'boolean'));
});
test('reset clears own key and UI, retaining unrelated storage', () => {
  const storage = memory(); storage.setItem('other-app', 'retained');
  const f = fixture(storage); f.first.checked = true; f.first.fire('change');
  f.reset.fire('click');
  assert.equal(f.meter.value, 0);
  assert.equal(storage.getItem(KEY), null);
  assert.equal(storage.getItem('other-app'), 'retained');
  assert.equal(fixture(storage).first.checked, false);
});
test('access to storage getter may throw; session checkboxes still work', () => {
  const f = fixture(() => { throw new Error('SecurityError'); });
  assert.match(f.notice.textContent, /unavailable/);
  f.first.checked = true; f.first.fire('change');
  assert.equal(f.meter.value, 1);
  f.reset.fire('click'); assert.equal(f.meter.value, 0);
});
test('getItem failure has readable session-only recovery', () => {
  const storage = memory(); storage.getItem = () => { throw new Error('denied'); };
  const f = fixture(storage); assert.match(f.notice.textContent, /unavailable/);
  f.first.checked = true; f.first.fire('change'); assert.equal(f.meter.value, 1);
});
test('quota/write failure leaves UI usable and warns about old saved state', () => {
  const storage = memory(); storage.setItem = () => { throw new Error('QuotaExceeded'); };
  const f = fixture(storage); f.first.checked = true; f.first.fire('change');
  assert.equal(f.meter.value, 1); assert.match(f.notice.textContent, /could not be saved/);
});
test('remove failure still resets visit but truthfully warns about reload', () => {
  const storage = memory(); const f = fixture(storage);
  f.first.checked = true; f.first.fire('change');
  storage.removeItem = () => { throw new Error('denied'); };
  f.reset.fire('click'); assert.equal(f.first.checked, false);
  assert.equal(f.meter.value, 0); assert.match(f.notice.textContent, /may return after reload/);
  assert.equal(fixture(storage).first.checked, true);
});
test('corruption ignores all progress and next toggle replaces invalid payload', () => {
  const storage = memory(); storage.setItem(KEY, '{"version":1,"steps":{"readiness":true,"secret":"example"}}');
  const f = fixture(storage); assert.equal(f.first.checked, false);
  assert.match(f.notice.textContent, /invalid/);
  f.first.checked = true; f.first.fire('change');
  assert.equal(parse(storage.getItem(KEY)).corrupt, false);
  assert.ok(!storage.getItem(KEY).includes('secret'));
});
test('complete message is not a provider certification', () => {
  const f = fixture(); for (const id of IDS) f.nodes.get('#step-' + id).checked = true;
  f.first.fire('change'); assert.equal(f.meter.value, 14);
  assert.match(f.count.textContent, /not automatic provider verification/);
});
test('unknown input text/credentials are never read or persisted', () => {
  const storage = memory(); const f = fixture(storage);
  f.nodes.set('#credential', { value: 'example-private-value' });
  f.first.value = 'example-private-value'; f.first.checked = true; f.first.fire('change');
  assert.ok(!storage.getItem(KEY).includes('example-private-value'));
});
test('missing DOM is harmless and leaves native fallback', () => {
  assert.doesNotThrow(() => init({ querySelector: () => null }, () => { throw new Error(); }));
});
