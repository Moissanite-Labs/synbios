'use strict';

// Exercise the shipped refresh function with controlled network completion order.
// Rendering is replaced with a spy; these are not browser or accessibility tests.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness() {
  const pending = [], rendered = [], elements = new Map();
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, {addEventListener() {}});
        return elements.get(id);
      },
    },
    setInterval() {},
    fetch(url) {
      // Leave normal startup pending so each test controls only explicit refreshes.
      if (url === '/api/session') return new Promise(() => {});
      assert.equal(url, '/api/status');
      return new Promise((resolve, reject) => pending.push({resolve, reject}));
    },
    captureRender(result) { rendered.push(result.sequence); },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8'), context);
  vm.runInContext('render = captureRender;', context);
  return {
    pending,
    rendered,
    refresh: () => vm.runInContext('refresh()', context),
    current: () => vm.runInContext('current', context),
    succeed(index, sequence) {
      pending[index].resolve({ok: true, json: async () => ({ok: true, result: {sequence}})});
    },
  };
}

test('an older successful refresh cannot replace a newer rendered snapshot', async () => {
  const h = harness();
  const earlier = h.refresh(), later = h.refresh();
  h.succeed(1, 2);
  await later;
  h.succeed(0, 1);
  await earlier;
  assert.deepEqual(h.rendered, [2]);
  assert.equal(h.current().sequence, 2);
});

test('an older failed refresh does not surface after a newer successful refresh', async () => {
  const h = harness();
  const earlier = h.refresh(), later = h.refresh();
  h.succeed(1, 2);
  await later;
  h.pending[0].reject(new Error('obsolete network failure'));
  await assert.doesNotReject(earlier);
  assert.deepEqual(h.rendered, [2]);
  assert.equal(h.current().sequence, 2);
});

test('the latest refresh failure remains visible to its caller', async () => {
  const h = harness();
  const initial = h.refresh();
  h.succeed(0, 1);
  await initial;
  const latest = h.refresh();
  h.pending[1].reject(new Error('current network failure'));
  await assert.rejects(latest, /current network failure/);
  assert.deepEqual(h.rendered, [1]);
  assert.equal(h.current().sequence, 1);
});
