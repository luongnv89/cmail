/* Progressive enhancement only: the guide and native checkboxes work without JS. */
(function () {
  'use strict';
  const KEY = 'cmail:setup-progress:v1';
  // Semantic IDs are allowlisted, never inferred from user input or page text.
  const IDS = Object.freeze(['readiness', 'install', 'dependencies', 'registrar',
    'zone', 'token', 'config', 'access', 'delegation', 'routing', 'destination',
    'rules', 'gmail', 'delivery']);

  function parse(raw) {
    if (raw === null) return { steps: {}, corrupt: false };
    try {
      const value = JSON.parse(raw);
      if (!value || Array.isArray(value) || value.version !== 1 ||
          Object.keys(value).some(key => !['version', 'steps'].includes(key)) ||
          !value.steps || typeof value.steps !== 'object' || Array.isArray(value.steps) ||
          Object.entries(value.steps).some(([id, done]) => !IDS.includes(id) || typeof done !== 'boolean')) {
        throw new Error('Invalid progress');
      }
      return { steps: value.steps, corrupt: false };
    } catch (_) {
      return { steps: {}, corrupt: true };
    }
  }

  function init(root, storage) {
    const inputs = IDS.map(id => root.querySelector('#step-' + id));
    const panel = root.querySelector('#progress-panel');
    const meter = root.querySelector('#setup-progress');
    const count = root.querySelector('#progress-count');
    const notice = root.querySelector('#storage-notice');
    const reset = root.querySelector('#reset-progress');
    if (inputs.some(input => !input) || !panel || !meter || !count || !notice || !reset) return;
    const saved = 'Progress is saved in this browser only. Only step IDs and booleans are stored.';
    let message = saved;
    let state = {};
    try {
      const loaded = parse(storage().getItem(KEY));
      state = loaded.steps;
      if (loaded.corrupt) message = 'Saved progress was invalid and has been ignored. Check steps again; the next change replaces it.';
    } catch (_) {
      message = 'Browser storage is unavailable. Checkboxes work for this visit; progress may not survive reload.';
    }
    inputs.forEach((input, i) => { input.checked = state[IDS[i]] === true; });
    function render() {
      const done = inputs.filter(input => input.checked).length;
      meter.max = IDS.length;
      meter.value = done;
      count.textContent = done + ' of ' + IDS.length + ' steps checked' +
        (done === IDS.length ? ' — review complete, not automatic provider verification.' : '.');
      notice.textContent = message;
    }
    function snapshot() {
      return { version: 1, steps: Object.fromEntries(inputs.map((input, i) => [IDS[i], input.checked])) };
    }
    inputs.forEach(input => input.addEventListener('change', () => {
      try {
        storage().setItem(KEY, JSON.stringify(snapshot()));
        message = saved;
      } catch (_) {
        message = 'Progress could not be saved. Checkboxes still work; older saved progress may return after reload.';
      }
      render();
    }));
    reset.addEventListener('click', () => {
      inputs.forEach(input => { input.checked = false; });
      try {
        // Never clear other applications' storage. Reset the UI even if removal fails.
        storage().removeItem(KEY);
        message = 'Progress reset. No provider settings or credentials were changed.';
      } catch (_) {
        message = 'Progress reset for this visit, but saved progress could not be removed and may return after reload.';
      }
      render();
    });
    render();
    panel.hidden = false;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { KEY, IDS, parse, init };
  if (typeof document !== 'undefined') init(document, () => window.localStorage);
}());
