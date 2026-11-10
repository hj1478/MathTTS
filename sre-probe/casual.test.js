// casual.js: the --casual rewrites, on LaTeX and on real SRE speech (plain + SSML).
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const sre = require('speech-rule-engine');
const temml = require('temml');

const { casualLatex, casualSpeech } = require('./casual');
const { checkWellFormed, fixMisreads } = require('./speak');

test('simple subscripts become one name; compound ones keep 아래첨자', () => {
  assert.strictEqual(casualLatex('A_1+A_{2}'), 'A{1}+A{2}');
  assert.strictEqual(casualLatex('S_{10}'), 'S{10}');
  assert.strictEqual(casualLatex('a_n=a_{ n }'), 'a{n}=a{n}');
  assert.strictEqual(casualLatex('x_{1}^{2}'), 'x{1}^{2}');
  assert.strictEqual(casualLatex('a_{n+1}'), 'a_{n+1}');
  assert.strictEqual(casualLatex('\\log_2 8'), '\\log_2 8'); // a command, not a variable
  assert.strictEqual(casualLatex("a_1'"), "a_1'");              // a{1}' is read "피트"
  assert.strictEqual(casualLatex('\\mathrm{A_1}+B_1'), '\\mathrm{A_1}+B{1}');  // a unit, not a variable
  assert.strictEqual(casualLatex('\\text{a_1}'), '\\text{a_1}');
});

async function say(latex, ssml, opts) {
  await sre.setupEngine({ locale: 'ko', domain: 'clearspeak', style: 'default',
                          modality: 'speech', markup: ssml ? 'ssml' : 'none' });
  await sre.engineReady();
  const xml = temml.renderToString(casualLatex(latex), { xml: true, throwOnError: true });
  return casualSpeech(fixMisreads(sre.toSpeech(xml)), opts).replace(/\s+/g, ' ').trim();
}

const CASES = [
  ['A_1', 'A 1'],
  ['a_{n+1}', 'a 아래첨자 n 플러스 1'],
  ['x_1+x_2', 'x 1 플러스 x 2'],
  ['\\frac{x+1}{x-1}', 'x 마이너스 1 분의 x 플러스 1'],
  ['\\frac{1}{2}', '2 분의 1'],
  ['f(x)=x^2+1', 'f x 는 x 제곱 플러스 1'],
  ["f'(x)", 'f 프라임 x'],
  ['a^{n}', 'a 의 n 제곱'],
  ['3(x-k)\\leq 2x+5', '3 괄호 열고 x 마이너스 k 괄호 닫고 는 2 x 플러스 5 이하'],
  ['x \\geq 3', 'x 는 3 이상'],
  ['x\\neq 0', 'x 는 0 이 아니다'],
  ['\\log_2 8', '로그 2 의 8'],
  ['\\{1,2,3\\}', '집합 1, 2, 3'],
  ['(-1)^{n}\\times(-1)^{m}', '괄호 열고 마이너스 1 괄호 닫고 의 n 제곱 곱하기 괄호 열고 마이너스 1 괄호 닫고 의 m 제곱'],
  ['B\\times C', 'B 곱하기 C'],
  // found in review, 2026-11-09
  ['x^{n+1}', 'x 의 n 플러스 1 제곱'],                     // a power, not "x n …"
  ['x^{ab}', 'x 의 a b 제곱'],
  ['f(x)+x^2', 'f 의 x 플러스 x 제곱'],                    // unsure: keep the 의
  ['\\log_a x', '로그 a 의 x'],                           // the base, in both modes
  ['\\frac{x+1}{x-1}=3', 'x 마이너스 1 분의 x 플러스 1 은 3'],  // 은 after 일
  ['\\frac{x-3}{2}\\neq 0', '2 분의 x 마이너스 3 은 0 이 아니다'],
  ['\\frac{1}{x}=2', 'x 분의 1 은 2'],
];

// SRE says 곱하기 for a written × too; speak.js passes keepTimes for such a span
const KEEP = [
  ['2\\times(3+4)', '2 곱하기 괄호 열고 3 플러스 4 괄호 닫고'],
];

for (const [latex, want] of CASES) {
  test(`plain: ${latex}`, async () => {
    assert.strictEqual((await say(latex, false)).replace(/ ,/g, ','), want);
  });
  test(`ssml stays well-formed and says the same: ${latex}`, async () => {
    const out = (await say(latex, true)).replace(/^<\?xml[^>]*\?>/, '');
    assert.strictEqual(checkWellFormed(out), null);
    const words = out.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    assert.strictEqual(words.replace(/ ,/g, ','), want);
  });
}

for (const [latex, want] of KEEP) {
  for (const ssml of [false, true]) {
    test(`keepTimes (${ssml ? 'ssml' : 'plain'}): ${latex}`, async () => {
      const out = (await say(latex, ssml, { keepTimes: true })).replace(/^<\?xml[^>]*\?>/, '');
      assert.strictEqual(out.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim(), want);
    });
  }
}
