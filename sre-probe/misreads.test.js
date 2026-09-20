/**
 * The post-SRE misread table (issue #20).
 *
 * Every rule here exists because SRE-ko was measured saying the "was" string
 * through the real chain; `python3 eval/notation_coverage.py` re-measures.
 * The point of the suite is the negative cases: these are blind string
 * rewrites over Korean speech, so each one has to be shown not to fire on a
 * span that was already correct.
 *
 * Run with:  node --test   (from inside sre-probe/)
 */

'use strict';

const { test } = require('node:test');
const assert = require('node:assert');

const { fixMisreads, fixPerp, perpAsParallel } = require('./speak.js');

test('glyphs named by their Unicode description are read as mathematics', () => {
  assert.equal(fixMisreads('흰색 정사각형 안에 알맞은 수'), '네모 안에 알맞은 수');
  assert.equal(fixMisreads('흰색 상향 삼각형 A B C'), '삼각형 A B C');
  assert.equal(fixMisreads('흰색 상향 삼각형 A B C 합동이다 흰색 상향 삼각형 D E F'),
               '삼각형 A B C 합동이다 삼각형 D E F');
});

test('Korean puts the power before the unit', () => {
  assert.equal(fixMisreads('12 센티미터 제곱'), '12 제곱센티미터');
  assert.equal(fixMisreads('8 센티미터 세제곱'), '8 세제곱센티미터');
  assert.equal(fixMisreads('3 밀리미터 제곱'), '3 제곱밀리미터');
});

test('the unit rule does not fire on a bare power', () => {
  // "x 제곱" and "5 센티미터" are both already correct; only the two adjacent
  // is the misreading.
  assert.equal(fixMisreads('x 제곱 더하기 y 제곱'), 'x 제곱 더하기 y 제곱');
  assert.equal(fixMisreads('5 센티미터'), '5 센티미터');
  assert.equal(fixMisreads('한 변이 5 센티미터 이고 넓이가 x 제곱'),
               '한 변이 5 센티미터 이고 넓이가 x 제곱');
});

test('trig functions take the textbook spelling', () => {
  assert.equal(fixMisreads('싸인 A'), '사인 A');
  assert.equal(fixMisreads('코싸인 30 도'), '코사인 30 도');
  assert.equal(fixMisreads('탄젠트 30 도'), '탄젠트 30 도');
});

test('perp borrows parallel\'s sentence frame only when unambiguous', () => {
  assert.equal(perpAsParallel('l \\perp m'), true);
  assert.equal(perpAsParallel('l \\parallel m'), false);
  // both relations in one span: rendering \perp as \parallel would make them
  // indistinguishable, so the span is left alone.
  assert.equal(perpAsParallel('l \\perp m, m \\parallel n'), false);
  assert.equal(perpAsParallel('a+b'), false);
});

test('fixPerp swaps the verb SRE produced for parallel', () => {
  assert.equal(fixPerp('l 은 m 과 평행하다'), 'l 은 m 과 수직이다');
  assert.equal(fixPerp('a 는 b 와 평행하다'), 'a 는 b 와 수직이다');
});
