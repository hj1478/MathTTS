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
        splitFences, splitChains, splitAbs, splitSpecials, endsWithJong,
        fixMisreads } = require('./speak.js');

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
  assert.strictEqual(fixMisreads('삼각형 A B C 역 물결표 삼각형 D E F'),
    '삼각형 A B C 닮음이다 삼각형 D E F');
  assert.strictEqual(fixMisreads('싸인 A 더하기 코싸인 B'), '사인 A 더하기 코사인 B');
});

test('only ∽ (\\sim, read via \\backsim) becomes 닮음이다, never the \\tilde accent', async () => {
  // a plain 물결표 is \tilde, even between operands: \tilde{x}+1 is "x 물결표 더하기 1"
  assert.strictEqual(fixMisreads('x 물결표 더하기 1'), 'x 물결표 더하기 1');
  assert.strictEqual(fixMisreads('x 물결표'), 'x 물결표');
  const run = (md) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sim-'));
    const f = path.join(dir, 'in.md');
    fs.writeFileSync(f, md);
    return execFileSync('node', [path.join(__dirname, 'speak.js'), '--combos', 'clearspeak/default', f],
                        { encoding: 'utf8' });
  };
  const out = run('$\\triangle ABC \\sim \\triangle DEF$ 이고 $\\tilde{x}+1$');
  assert.match(out, /삼각형 A B C 닮음이다 삼각형 D E F/);
  assert.match(out, /x 물결표 더하기 1/);
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

test('splitChains takes fractions, roots, π and absolute values as terms', () => {
  assert.deepStrictEqual(splitChains('0<x<\\pi'),
    [{ latex: '0 < x' }, { text: ',' }, { latex: 'x < \\pi' }]);
  assert.deepStrictEqual(splitChains('\\frac{1}{2}<x<\\frac{3}{2}'),
    [{ latex: '\\frac{1}{2} < x' }, { text: ',' }, { latex: 'x < \\frac{3}{2}' }]);
  assert.deepStrictEqual(splitChains('-\\frac12\\le x\\le 1'),
    [{ latex: '-\\frac12 \\le x' }, { text: ',' }, { latex: 'x \\le 1' }]);
  assert.deepStrictEqual(splitChains('3<|x-1|<5'),
    [{ latex: '3 < |x-1|' }, { text: ',' }, { latex: '|x-1| < 5' }]);
  // \left is not \le
  assert.deepStrictEqual(splitChains('\\left|x\\right|<1'), [{ latex: '\\left|x\\right|<1' }]);
});

test('splitAbs: a coefficient is spoken as 곱하기, a relation keeps the prefix reading', () => {
  // 2|x-1| must not sound like |2x-1| ("2 x 빼기 1 의 절댓값")
  assert.deepStrictEqual(splitAbs('2|x-1|'),
    [{ latex: '2' }, { text: '곱하기' }, { latex: 'x-1' }, { text: '의 절댓값' }]);
  assert.deepStrictEqual(splitAbs('a-|x-1|'),
    [{ latex: 'a-' }, { latex: 'x-1' }, { text: '의 절댓값' }]);
  // moving 절댓값 would strand "3 <" as "3 은 보다 작다"
  assert.deepStrictEqual(splitAbs('3 < |x-1|'), [{ latex: '3 < |x-1|' }]);
  assert.deepStrictEqual(splitAbs('|x-1| < 5'),
    [{ latex: 'x-1' }, { text: '의 절댓값' }, { latex: ' < 5' }]);
});

test('splitSpecials turns a dangling sign minus into its own word', () => {
  assert.deepStrictEqual(splitSpecials('y=-|x-1|+3', false),
    [{ latex: 'y=' }, { text: '마이너스', sign: true }, { latex: 'x-1' },
     { text: '의 절댓값' }, { latex: '+3' }]);
  assert.deepStrictEqual(splitSpecials('-0.\\dot{3}', false),
    [{ text: '마이너스', sign: true }, { text: '영 점 삼 삼 반복' }]);
  // between two roots the minus is binary and stays latex
  assert.deepStrictEqual(splitSpecials('\\sqrt{a+b}-\\sqrt{a-b}', true),
    [{ root: 'a+b' }, { latex: '-' }, { root: 'a-b' }]);
});

test('splitRepeating reads the integer part as a number', () => {
  assert.deepStrictEqual(splitRepeating('12.\\dot{5}'), [{ text: '십이 점 오 오 반복' }]);
  assert.deepStrictEqual(splitRepeating('105.\\dot{2}'), [{ text: '백오 점 이 이 반복' }]);
  assert.deepStrictEqual(splitRepeating('10.\\dot{1}'), [{ text: '십 점 일 일 반복' }]);
  assert.deepStrictEqual(splitRepeating('3.\\dot{1}'), [{ text: '삼 점 일 일 반복' }]);
});

test('endsWithJong follows the last SPOKEN word', () => {
  assert.strictEqual(endsWithJong('루트 x 더하기 1'), true);     // 일
  assert.strictEqual(endsWithJong('루트 x 더하기 2'), false);    // 이
  assert.strictEqual(endsWithJong('10'), true);                  // 십
  assert.strictEqual(endsWithJong('선분 P R'), true);            // 알
  assert.strictEqual(endsWithJong('선분 A D'), false);           // 디
  assert.strictEqual(endsWithJong(' 루트 \x01<say-as interpret-as="characters">x</say-as> 더하기 1\x02 '),
    true);                                                       // markup + voice markers
  assert.strictEqual(endsWithJong('의 절댓값'), true);
});

// End to end through temml + SRE: what the listener actually hears.
const { execFileSync } = require('child_process');
const os = require('os');

function stitch(lines, mode) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'speak-test-'));
  try {
    fs.writeFileSync(path.join(dir, 't.norm.md'), lines.join('\n\n'));
    const args = [path.join(__dirname, 'speak.js'), '--combos', 'clearspeak/default',
                  '--write', dir, path.join(dir, 't.norm.md')];
    if (mode) args.splice(1, 0, mode);
    execFileSync(process.execPath, args, { encoding: 'utf8' });
    const read = (ext) => fs.readFileSync(path.join(dir, `t.stitched.${ext}`), 'utf8');
    const strip = (s) => s.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    if (mode === '--both') return { txt: read('txt'), ssml: read('ssml') };
    return mode === '--ssml' ? strip(read('ssml')).split(/ (?=[A-Z]\) )/)
                             : read('txt').trim().split(/\n+/).map((l) => l.trim());
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test('speech: a leading minus is a sign, not 빼기', () => {
  const [a, b, c, d] = stitch(['$-2<x<3$', '$y=-|x-1|+3$', '$-0.\\dot{3}$', '$\\sqrt{a+b}+1$']);
  assert.strictEqual(a, '마이너스 2 는 x 보다 작다 , x 는 3 보다 작다');
  assert.strictEqual(b, 'y 는 마이너스 x 빼기 1 의 절댓값 더하기 3');
  assert.strictEqual(c, '마이너스 영 점 삼 삼 반복');
  assert.strictEqual(d, '루트 a 더하기 b 더하기 1');           // binary after an operand
});

test('speech: chains keep their particles; |..| coefficients are spoken', () => {
  const [a, b, c, d] = stitch(['$0<x<\\pi$', '$\\frac{1}{2}<x<\\frac{3}{2}$',
                               '$3<|x-1|<5$', '$2|x-1|$']);
  assert.strictEqual(a, '0 은 x 보다 작다 , x 는 파이 보다 작다');
  assert.strictEqual(b, '2 분의 1 은 x 보다 작다 , x 는 2 분의 3 보다 작다');
  assert.strictEqual(c, '3 은 절댓값 x 빼기 1 보다 작다 , x 빼기 1 의 절댓값 은 5 보다 작다');
  assert.strictEqual(d, '2 곱하기 x 빼기 1 의 절댓값');
});

test('speech (SSML): sign and 은/는 across a radical split', () => {
  const [a, b] = stitch(['A) $-\\sqrt{x+1}$', 'B) $\\sqrt{x+1}=3$'], '--ssml');
  assert.strictEqual(a, 'A) 마이너스 루트 x 더하기 1');
  assert.strictEqual(b, 'B) 루트 x 더하기 1 은 3');
});

test('--both writes the same files as separate plain and --ssml runs', () => {
  const lines = ['문제 $-2<x<3$ 일 때', '$\\sqrt{a+b}-\\sqrt{a-b}=2|x-1|$'];
  const both = stitch(lines, '--both');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'speak-test-'));
  try {
    fs.writeFileSync(path.join(dir, 't.norm.md'), lines.join('\n\n'));
    for (const extra of [[], ['--ssml']]) {
      execFileSync(process.execPath, [path.join(__dirname, 'speak.js'), ...extra, '--combos',
        'clearspeak/default', '--write', dir, path.join(dir, 't.norm.md')]);
    }
    assert.strictEqual(both.txt, fs.readFileSync(path.join(dir, 't.stitched.txt'), 'utf8'));
    assert.strictEqual(both.ssml, fs.readFileSync(path.join(dir, 't.stitched.ssml'), 'utf8'));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
