/**
 * --casual: math read the way a teacher says it aloud, not the way a screen
 * reader spells it out. SRE's Korean clearspeak is exact but long-winded
 * ("A 아래첨자 1", "분모가 x 빼기 1 이고 분자가 x 더하기 1 인 분수"); a person
 * says "A 1" and "x 마이너스 1 분의 x 플러스 1".
 *
 * Two layers:
 *   casualLatex()   before temml/SRE: rewrites the LaTeX so SRE never produces
 *                   the long form (simple subscripts).
 *   casualSpeech()  after SRE, on one span's speech: phrase-level shortenings.
 *                   Works on plain text AND on SRE's SSML (tags such as
 *                   <say-as>, <prosody>, <break/> may sit between the words),
 *                   so every pattern lets markup through between tokens.
 *
 * Only math speech is rewritten, never the problem's prose ("빼기" in a
 * sentence stays).
 */
'use strict';

/* ------------------------------ LaTeX layer ------------------------------ */

// A one-letter variable (not the tail of a command such as \log) with a
// subscript that is a number or a single letter: x_1, a_{n}, S_{10}, x_{1}^{2}.
// Written as a group instead, x{1}, SRE reads it "x 1" — said as one name,
// "엑스 일". A compound subscript (a_{n+1}) keeps 아래첨자: without it,
// a_{n+1} and a_n+1 would sound the same.
// Not before a prime: a{1}' is read "a 1 피트" (feet), so a_1' keeps 아래첨자.
const SIMPLE_SUB = /(?<![\\A-Za-z])([A-Za-z])_(?:\{\s*([A-Za-z]|\d+)\s*\}|([A-Za-z0-9]))(?!\s*')/;
// Inside \mathrm{} / \text{} a letter is a unit or a word, not a variable:
// \mathrm{A_1} as \mathrm{A{1}} is read "암페어 곱하기 1". Those groups are skipped.
const UPRIGHT = String.raw`\\(?:text|mathrm|textrm|mbox|operatorname)\s*\{[^{}]*\}`;
const LATEX_RE = new RegExp(`${UPRIGHT}|${SIMPLE_SUB.source}`, 'g');

function casualLatex(latex) {
  return latex.replace(LATEX_RE, (m, base, braced, bare) =>
    base === undefined ? m : `${base}{${braced ?? bare}}`);
}

/* ------------------------------ speech layer ----------------------------- */

// Between two spoken words in SSML there may be markup. A rule may swallow
// spaces and <break/> pauses (SOFT), never other tags: dropping a </prosody>
// would break the XML. Where it only looks ahead it lets any tag through (GAP).
const SOFT = String.raw`(?:\s|<break[^>]*/>)*`;
const GAP = String.raw`(?:\s|<[^>]*>)*`;
const re = (s, flags = 'g') => new RegExp(s.replace(/ /g, SOFT), flags);
// One spoken letter, bare or wrapped in <say-as>: "x" or <say-as ...>x</say-as>
const LETTER = String.raw`(?:<say-as[^>]*>[A-Za-z]</say-as>|(?<![A-Za-z])[A-Za-z](?![A-Za-z]))`;
// A run of speech that does not reach into another fraction
const PART = String.raw`((?:(?!분모가|분자가|분수).)+?)`;

// Whether the last spoken word has a 받침, for re-picking 은/는 after a rewrite
// (the same rule as speak.js endsWithJong): digits 영 일 삼 육 칠 팔, the
// letters 엘 엠 엔 알, or the last Hangul syllable.
function hasJong(s) {
  const t = s.replace(/<[^>]*>/g, ' ').trimEnd();
  const c = t[t.length - 1] ?? '';
  if (/[0-9]/.test(c)) return '013678'.includes(c);
  if (/[A-Za-z]/.test(c)) return 'lmnrLMNR'.includes(c);
  if (/[가-힣]/.test(c)) return (c.charCodeAt(0) - 0xac00) % 28 !== 0;
  return null;
}
// SRE picked 는 for "…인 분수 는"; the rewrite ends on the numerator instead
const fraction = (_m, den, num, gap, particle) => {
  if (!particle) return ` ${den} 분의 ${num} ${gap}`;  // gap may hold tags: keep them
  const jong = hasJong(num);
  return ` ${den} 분의 ${num} ${gap}${jong === null ? particle : jong ? '은' : '는'}`;
};
// A word that ends the operand of f (a relation or a list): a 제곱 after it
// belongs to something else. Before it, a 제곱 means "x 의 n 더하기 1 제곱", a power.
const ENDS_ARG = '는|은|이고|이상|이하|보다|아니다|콤마|,|과|와|괄호';

const RULES = [
  // fractions: "분모가 B 이고 분자가 A 인 분수" -> "B 분의 A", as for simple
  // fractions (SRE already says "2 분의 1"). A nested fraction keeps the long form.
  [re(`분모가 ${PART} 이고 분자가 ${PART} 인 분수(${GAP})(는|은)?(?=\\s|<|$)`, 'gs'), fraction],
  // + and - inside math: 플러스 / 마이너스 is what is said in class
  [/더하기/g, '플러스'],
  [/빼기/g, '마이너스'],
  // implied multiplication before a bracket: "3(x-k)" is "3 괄호 열고 …".
  // Only right after a number or a letter: after "제곱" or "괄호 닫고" the 곱하기
  // is a written × that must stay ("(-1)^n × (-1)^m").
  // SRE says 곱하기 for a written × too, so a span with \times / \cdot (or a
  // 곱하기 speak.js put in itself) keeps every one: opts.keepTimes.
  [new RegExp(`(?<=(?:\\d|(?<![A-Za-z])[A-Za-z]|</say-as>)${GAP})곱하기${SOFT}(?=괄호 열고)`, 'g'), '', 'times'],
  // inequalities with "or equal": 이상 / 이하
  [re(`보다 크거나 같다`), ' 이상 '],
  [re(`보다 작거나 같다`), ' 이하 '],
  // "0 과 같지 않다" -> "0 이 아니다" (과/와 already carries the 받침)
  [re(`과 같지 않다`), ' 이 아니다 '],
  [re(`와 같지 않다`), ' 가 아니다 '],
  // logarithm: "밑이 2 인 로그 의 8" -> "로그 2 의 8"
  // (in SSML the base is wrapped: <say-as …>a</say-as>, which has spaces)
  [re(`밑이 ((?:<say-as[^>]*>[^<]*</say-as>|\\S)+?) 인 로그`), ' 로그 $1 '],
  // function application: "f 의 x" -> "f x", "f 프라임 의 x" -> "f 프라임 x".
  // Not before another 의, and not when a 제곱 follows before the argument
  // ends: SRE reads x^{n+1} as "x 의 n 더하기 1 제곱", a power. (f(x)^2, "f 의 x
  // 제곱", keeps its 의 too; SRE's own reading of it is already ambiguous.)
  // Not after 로그 either: "로그 a 의 x" is log base a of x, not a product.
  [new RegExp(`(?<!로그${GAP})(${LETTER}|프라임)(${GAP})의${SOFT}(?=${GAP}${LETTER}`
              + `(?!${GAP}의)(?!(?:(?!${ENDS_ARG}).)*?제곱))`, 'gs'),
   '$1$2 '],
  // lists: a comma is a pause, not a word
  [/ 콤마 /g, ', '],
];

function casualSpeech(speech, opts = {}) {
  let out = speech;
  for (const [pattern, to, kind] of RULES) {
    if (kind === 'times' && opts.keepTimes) continue;
    out = out.replace(pattern, to);
  }
  return out.replace(/ {2,}/g, ' ');
}

module.exports = { casualLatex, casualSpeech };
