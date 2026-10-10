/* Progressive enhancement only: terminal text is fully readable without JS.
   Adds a Replay button that reveals a session line by line. Respects reduced motion. */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Split <pre> content into block-level line spans, moving (not copying) nodes.
  function wrapLines(pre) {
    const lines = [];
    let line = newLine();
    Array.from(pre.childNodes).forEach(node => {
      if (node.nodeType !== 3) { line.appendChild(node); return; }
      node.data.split('\n').forEach((part, i) => {
        if (i > 0) { lines.push(line); line = newLine(); }
        if (part) line.appendChild(document.createTextNode(part));
      });
    });
    lines.push(line);
    pre.textContent = '';
    lines.forEach(item => {
      if (!item.childNodes.length) item.appendChild(document.createTextNode(' '));
      pre.appendChild(item);
    });
    return lines;
  }
  function newLine() { const span = document.createElement('span'); span.className = 'ln'; return span; }

  function setup(term) {
    const pre = term.querySelector('pre');
    const bar = term.querySelector('.term-bar');
    if (!pre || !bar) return;
    const lines = wrapLines(pre);
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Replay';
    bar.removeAttribute('aria-hidden');
    bar.querySelectorAll('i, span').forEach(el => el.setAttribute('aria-hidden', 'true'));
    bar.appendChild(button);
    let timer = null;
    function finish() {
      clearTimeout(timer);
      term.classList.remove('playing');
      button.textContent = 'Replay';
    }
    function play() {
      if (term.classList.contains('playing')) { finish(); return; }
      lines.forEach(line => line.classList.remove('on'));
      term.classList.add('playing');
      button.textContent = 'Skip';
      pre.scrollTop = 0;
      let i = 0;
      (function next() {
        if (i >= lines.length) { finish(); return; }
        const line = lines[i++];
        line.classList.add('on');
        const top = line.offsetTop - pre.clientHeight + line.offsetHeight + 16;
        if (top > pre.scrollTop) pre.scrollTop = top;
        const text = line.textContent;
        // Pause longer on prompts and section headers so the flow is easy to follow.
        const delay = text.indexOf(' ?') === 0 || text.indexOf(' !') === 0 ? 900 : text.indexOf('──') === 0 ? 500 : 140;
        timer = setTimeout(next, delay);
      }());
    }
    button.addEventListener('click', play);
    if (!reduced && 'IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); play(); }
      }, { threshold: 0.35 });
      observer.observe(term);
    }
  }

  document.querySelectorAll('.term[data-replay]').forEach(setup);
}());
