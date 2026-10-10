'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../docs/assets/terminal.js'), 'utf8');

function fixture(documentTop) {
  const lineHeight = 20;
  const padding = 16;
  const timers = new Map();
  let timerId = 0;
  function element() {
    const classes = new Set();
    return {
      childNodes: [], listeners: {},
      classList: { add: value => classes.add(value), remove: value => classes.delete(value),
        contains: value => classes.has(value) },
      appendChild(node) { this.childNodes.push(node); },
      addEventListener(type, callback) { this.listeners[type] = callback; },
      get textContent() { return this.childNodes.map(node => node.textContent).join(''); },
      set textContent(text) { this.childNodes = text ? [textNode(text)] : []; }
    };
  }
  function textNode(text) { return { nodeType: 3, data: text, textContent: text }; }
  const pre = element();
  pre.textContent = Array.from({ length: 30 }, (_, i) => 'line ' + i).join('\n');
  pre.clientHeight = 120;
  let scrollTop = 0;
  Object.defineProperty(pre, 'scrollTop', {
    get: () => scrollTop,
    set: value => { scrollTop = Math.max(0, Math.min(value, 30 * lineHeight + 2 * padding - pre.clientHeight)); }
  });
  pre.getBoundingClientRect = () => ({ top: documentTop });
  const bar = { appendChild(button) { this.button = button; },
    removeAttribute() {}, querySelectorAll: () => [] };
  const term = element();
  term.querySelector = selector => selector === 'pre' ? pre : bar;
  const document = {
    querySelectorAll: () => [term], createTextNode: textNode,
    createElement(tag) {
      const node = element();
      if (tag === 'span') {
        // With an unpositioned pre, offsetTop is relative to the distant body.
        Object.defineProperty(node, 'offsetTop', {
          get: () => documentTop + padding + pre.childNodes.indexOf(node) * lineHeight
        });
        node.offsetHeight = lineHeight;
        node.getBoundingClientRect = () => ({ bottom: node.offsetTop + lineHeight - pre.scrollTop });
      }
      return node;
    }
  };
  vm.runInNewContext(source, { document, window: { matchMedia: () => ({ matches: true }) },
    setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
    clearTimeout(id) { timers.delete(id); } });
  return { pre, button: bar.button,
    tick() { const [id, callback] = timers.entries().next().value; timers.delete(id); callback(); } };
}

for (const documentTop of [0, 4000]) {
  test('replay reveals lines within its own scroll viewport at document offset ' + documentTop, () => {
    const f = fixture(documentTop);
    f.pre.scrollTop = 10000;
    f.button.listeners.click();
    assert.equal(f.pre.scrollTop, 0, 'replay starts with the first line visible');
    assert.ok(f.pre.childNodes[0].classList.contains('on'));
    for (let i = 1; i < 30; i++) {
      f.tick();
      assert.ok(f.pre.childNodes[i].classList.contains('on'));
      const top = 16 + i * 20;
      assert.ok(top >= f.pre.scrollTop, 'current line is not above the viewport');
      assert.ok(top + 20 <= f.pre.scrollTop + f.pre.clientHeight, 'current line is not below the viewport');
    }
    assert.ok(f.pre.scrollTop > 0, 'later lines scroll into view');
    f.tick();
    assert.equal(f.button.textContent, 'Replay');
  });
}
