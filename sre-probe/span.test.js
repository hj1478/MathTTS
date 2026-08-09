/**
 * JS side of the shared span-grammar check (issue #4).
 *
 * speak.js keeps a JS copy of normalize.py's SPAN rule (Python and JS cannot
 * share a regex). Both suites read ../eval/fixtures/span_cases.json and must
 * find the same spans; tests/test_span_grammar.py is the Python side.
 *
 * Run with:  node --test   (from inside sre-probe/)
 */

'use strict';

const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const { SPAN } = require('./speak.js');

const cases = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', 'eval', 'fixtures', 'span_cases.json'), 'utf8')
);

for (const c of cases) {
  test(`span grammar: ${c.name}`, () => {
    const found = [...c.text.matchAll(SPAN)].map((m) => m[0]);
    assert.deepStrictEqual(found, c.spans);
  });
}
