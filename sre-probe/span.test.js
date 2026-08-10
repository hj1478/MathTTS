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

const { SPAN, checkWellFormed, splitRadicals, splitRepeating } = require('./speak.js');

const cases = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', 'eval', 'fixtures', 'span_cases.json'), 'utf8')
);

for (const c of cases) {
  test(`span grammar: ${c.name}`, () => {
    const found = [...c.text.matchAll(SPAN)].map((m) => m[0]);
    assert.deepStrictEqual(found, c.spans);
  });
}

test('checkWellFormed accepts a real Azure envelope', () => {
  const ok =
    '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ko-KR">' +
    '<voice name="ko-KR-SunHiNeural">값은 <say-as interpret-as="characters">x</say-as>' +
    ' <break time="250ms"/> 3 &lt; 4 입니다</voice></speak>';
  assert.strictEqual(checkWellFormed(ok), null);
});

test('checkWellFormed rejects bad nesting, unclosed tags, stray characters', () => {
  assert.match(checkWellFormed('<speak><voice></speak></voice>'), /closes/);
  assert.match(checkWellFormed('<speak><voice>x</voice>'), /unclosed/);
  assert.match(checkWellFormed('<speak>a &amp b</speak>'), /bare '&'/);
  assert.match(checkWellFormed('<speak>a < b</speak>'), /unparseable tag/);
});

test('splitRadicals leaves simple radicands whole', () => {
  assert.deepStrictEqual(splitRadicals('\\sqrt{2}'), [{ latex: '\\sqrt{2}' }]);
  assert.deepStrictEqual(splitRadicals('x+1'), [{ latex: 'x+1' }]);
});

test('splitRadicals marks a complex radicand', () => {
  assert.deepStrictEqual(splitRadicals('\\sqrt{3+2\\sqrt{2}}'),
    [{ root: '3+2\\sqrt{2}' }]);
});

test('splitRadicals keeps surrounding latex as segments', () => {
  assert.deepStrictEqual(splitRadicals('x=\\sqrt{a+b}+1'),
    [{ latex: 'x=' }, { root: 'a+b' }, { latex: '+1' }]);
});

test('splitRadicals drops a paren pair wrapping the whole radicand', () => {
  assert.deepStrictEqual(splitRadicals('\\sqrt{(a+b)}'), [{ root: 'a+b' }]);
  // parens NOT wrapping the whole radicand stay
  assert.deepStrictEqual(splitRadicals('\\sqrt{(a+b)(c+d)}'),
    [{ root: '(a+b)(c+d)' }]);
});

test('splitRepeating speaks reading C for repeating decimals (provisional, #17)', () => {
  assert.deepStrictEqual(splitRepeating('0.\\dot{2}\\dot{4}'),
    [{ text: '영 점 이사 이사 반복' }]);
  // partial repetend: the 1 does not repeat
  assert.deepStrictEqual(splitRepeating('0.1\\dot{2}\\dot{3}'),
    [{ text: '영 점 일 이삼 이삼 반복' }]);
  // ambiguity foil: whole fractional part repeats
  assert.deepStrictEqual(splitRepeating('0.\\dot{1}2\\dot{3}'),
    [{ text: '영 점 일이삼 일이삼 반복' }]);
  assert.deepStrictEqual(splitRepeating('1.\\overline{23}'),
    [{ text: '일 점 이삼 이삼 반복' }]);
});

test('splitRepeating keeps surrounding latex and plain decimals', () => {
  assert.deepStrictEqual(splitRepeating('0.\\dot{3}=\\frac{1}{3}'),
    [{ text: '영 점 삼 삼 반복' }, { latex: '=\\frac{1}{3}' }]);
  assert.deepStrictEqual(splitRepeating('0.24+x'), [{ latex: '0.24+x' }]);
});
