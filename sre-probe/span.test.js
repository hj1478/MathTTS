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

const { SPAN, checkWellFormed, splitRadicals, splitRepeating, splitSegments,
        splitFences, splitChains, splitAbs, splitSubscripts,
        styleFor, fixMisreads } = require('./speak.js');

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

test('splitRepeating speaks reading C for repeating decimals (#17, decided)', () => {
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

test('fixMisreads puts the exponent first on units and reads a ratio as 대', () => {
  assert.strictEqual(fixMisreads('36 파이 센티미터 제곱'), '36 파이 제곱센티미터');
  assert.strictEqual(fixMisreads('8 센티미터 세제곱'), '8 세제곱센티미터');
  assert.strictEqual(fixMisreads('5 킬로미터 제곱'), '5 제곱킬로미터');
  assert.strictEqual(fixMisreads('3 콜론 4'), '3 대 4');
  assert.strictEqual(fixMisreads('3 콜론 4 콜론 5'), '3 대 4 대 5');   // chains
  assert.strictEqual(fixMisreads('흰색 정사각형 안에'), '네모 안에');  // still works
});

test('splitSegments reads \\overline over letters as 선분, decimals unaffected', () => {
  assert.deepStrictEqual(splitSegments('\\overline{AB}'), [{ text: '선분 A B' }]);
  assert.deepStrictEqual(splitSegments('\\overline{ABC}'), [{ text: '선분 A B C' }]);
  assert.deepStrictEqual(splitSegments('\\overline{AB}=\\overline{CD}'),
    [{ text: '선분 A B' }, { latex: '=' }, { text: '선분 C D' }]);
  // digits are 순환소수, handled by splitRepeating before this runs
  assert.deepStrictEqual(splitSegments('1.\\overline{23}'), [{ latex: '1.\\overline{23}' }]);
});

test('fixMisreads clears the remaining #20 geometry misreads', () => {
  assert.strictEqual(fixMisreads('흰색 상향 삼각형 A B C'), '삼각형 A B C');
  assert.strictEqual(fixMisreads('삼각형 A B C 물결표 삼각형 D E F'),
    '삼각형 A B C 닮음이다 삼각형 D E F');
  assert.strictEqual(fixMisreads('싸인 A 더하기 코싸인 B'), '사인 A 더하기 코사인 B');
});

test('fixMisreads rewrites only a BINARY 물결표, never the \\tilde accent', () => {
  assert.strictEqual(fixMisreads('삼각형 A B C 물결표 삼각형 D E F'),
    '삼각형 A B C 닮음이다 삼각형 D E F');
  assert.strictEqual(fixMisreads('x 물결표'), 'x 물결표');   // \tilde{x}, not 닮음
});

test('splitFences speaks a numeric tuple/interval and orders ⊥ with particles', () => {
  assert.deepStrictEqual(splitFences('(3,4)'), [{ text: '괄호 열고 3 콤마 4 괄호 닫고' }]);
  assert.deepStrictEqual(splitFences('(-2, 5)'),
    [{ text: '괄호 열고 마이너스 2 콤마 5 괄호 닫고' }]);
  assert.deepStrictEqual(splitFences('[3,4]'), [{ text: '대괄호 열고 3 콤마 4 대괄호 닫고' }]);
  // 받침 of the KOREAN reading picks the particle: l is 엘, a is 에이
  assert.deepStrictEqual(splitFences('l \\perp m'), [{ text: 'l 은 m 과 수직이다' }]);
  assert.deepStrictEqual(splitFences('a \\perp b'), [{ text: 'a 는 b 와 수직이다' }]);
  // symbolic tuples already keep their fence in SRE — left alone
  assert.deepStrictEqual(splitFences('(a,b)'), [{ latex: '(a,b)' }]);
  assert.deepStrictEqual(splitFences('(3]'), [{ latex: '(3]' }]);   // mismatched
});

test('splitChains restores particles by splitting into binary relations', () => {
  assert.deepStrictEqual(splitChains('p \\leq k<q'),
    [{ latex: 'p \\leq k' }, { text: ',' }, { latex: 'k < q' }]);
  assert.deepStrictEqual(splitChains('x \\leq 3'), [{ latex: 'x \\leq 3' }]);  // binary is fine
});

test('splitAbs moves 절댓값 after a COMPLEX operand only', () => {
  assert.deepStrictEqual(splitAbs('|x-2|+3'),
    [{ latex: 'x-2' }, { text: '의 절댓값' }, { latex: '+3' }]);
  assert.deepStrictEqual(splitAbs('|-4|'), [{ latex: '|-4|' }]);      // already unambiguous
  assert.deepStrictEqual(splitAbs('|a|+|b|'), [{ latex: '|a|+|b|' }]);
});

test('BATCHIM follows the sound, not the spelling', () => {
  // SRE itself says "x 는 3 보다", "s 는", "f 는" — 엑스/에스/에프 end without 받침
  assert.deepStrictEqual(splitFences('x \\perp y'), [{ text: 'x 는 y 와 수직이다' }]);
  assert.deepStrictEqual(splitFences('l \\perp m'), [{ text: 'l 은 m 과 수직이다' }]);
});

test('splitChains consumes the WHOLE chain, however many links', () => {
  // a 3-relation chain used to leave a dangling " \leq r" that spoke as a
  // clause with no subject: "..., k 는 q 보다 작거나 같다 는 r 보다 작거나 같다"
  assert.deepStrictEqual(splitChains('p \\leq k \\leq q \\leq r'),
    [{ latex: 'p \\leq k' }, { text: ',' }, { latex: 'k \\leq q' },
     { text: ',' }, { latex: 'q \\leq r' }]);
  // and must not start matching INSIDE a term: "x^2" was sliced to "x^" + "2"
  assert.deepStrictEqual(splitChains('x^2<y<z'),
    [{ latex: 'x^2 < y' }, { text: ',' }, { latex: 'y < z' }]);
});

test('styleFor enables a 시작/끝 form only for the structure actually nested', () => {
  assert.strictEqual(styleFor('\\frac{\\frac{1}{2}}{3}', 'default'), 'Fraction_GeneralEndFrac');
  // BOTH \frac arguments must be scanned, or this reads as un-nested
  assert.strictEqual(styleFor('\\frac{1}{\\frac{2}{3}}', 'default'), 'Fraction_GeneralEndFrac');
  assert.strictEqual(styleFor('\\sqrt{3+2\\sqrt{2}}', 'default'), 'Roots_RootEnd');
  assert.strictEqual(styleFor('2^{3^2}', 'default'), 'Exponent_AfterPower');
  // terse cases stay terse — siblings are not nesting, a bare root is not complex
  assert.strictEqual(styleFor('\\frac{3}{5}', 'default'), 'default');
  assert.strictEqual(styleFor('\\frac{1}{2}+\\frac{3}{4}', 'default'), 'default');
  assert.strictEqual(styleFor('\\sqrt{2}', 'default'), 'default');
  assert.strictEqual(styleFor('x^2', 'default'), 'default');
});

test('splitSubscripts says the index before the base, complex only', () => {
  assert.deepStrictEqual(splitSubscripts('x_{n+1}'),
    [{ latex: 'n+1' }, { text: '번째 x' }]);
  assert.deepStrictEqual(splitSubscripts('a_n'), [{ latex: 'a_n' }]);
});
