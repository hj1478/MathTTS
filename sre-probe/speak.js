/**
 * Feed normalized OCR markdown (normalize.py output) into the SRE Korean chain.
 *
 * Per file:  extract $...$ / $$...$$ spans -> temml -> MathML -> SRE (locale ko)
 * Prints:
 *   1. per-span table: LaTeX -> Korean speech in each requested domain/style
 *   2. STITCHED view: the full problem text with every math span replaced by its
 *      Korean speech — eyeball this; it is what a TTS voice would eventually read.
 *
 * Still a probe: no TTS, no audio, output is for inspection only.
 *
 * Usage:
 *   node speak.js "../output/kr question 1.norm.md" [more files...]
 *   node speak.js --dir ../output              # every *.norm.md in the folder
 *   node speak.js --combos mathspeak/sbrief,clearspeak/default --dir ../output
 *   node speak.js --ssml [--voice ko-KR-SunHiNeural] --dir ../output
 *   node speak.js --both --write OUT f.norm.md    # plain .txt AND .ssml, one process
 *
 * Default combos: clearspeak/default (natural register, used for the stitched
 * view) and mathspeak/default (unambiguous register), per the index.js probe.
 * Only the FIRST combo reaches the stitched output; the rest are for the table.
 *
 * --casual: read math as a person says it ("A 1", "x 마이너스 1 분의 x 플러스
 * 1", "3 이상") instead of SRE's spelled-out form; the rules are in casual.js.
 *
 * --both: the plain pass, then the --ssml pass, in one process (temml runs
 * once; the files written are the same as two separate runs). The SSML pass's
 * SUMMARY lines are prefixed "(ssml) ", and the exit status covers both.
 *
 * --ssml: SRE emits SSML per span (its own structural <break>s + <say-as> around
 * identifiers). SRE's envelope is <speak version="1.1" xml:lang="ko"> with no
 * <voice>, which Azure rejects — so the stitched view strips each span down to
 * its inner markup and re-wraps the whole document in the Azure envelope
 * (version="1.0", xml:lang="ko-KR", <voice name=...>). Prose is XML-escaped.
 * SRE writes interpret-as="character"; Azure documents only "characters"
 * (checked against learn.microsoft.com 2026-08), so ssmlInner() rewrites the
 * attribute during the re-wrap. An A/B ear check with tts_probe.py is still
 * the way to confirm the say-as tags audibly change anything.
 *
 * Radical grouping by voice (--ssml only): a \sqrt with a complex radicand is
 * stitched as "루트" + the radicand's speech inside a <voice> of the OPPOSITE
 * gender (--alt-voice overrides the default SunHi<->InJoon pairing). The voice
 * change marks where the root starts and ends, so no grouping parentheses are
 * spoken — a paren pair wrapping the whole radicand is dropped outright. The
 * plain-text path cannot switch voices and is unchanged (still ambiguous for
 * nested radicals — the known nested-radical-grouping gap).
 *
 * Repeating decimals (순환소수, both modes): \dot{}/​\overline{} decimals are
 * spoken as reading C from the #17 experiment ("영 점 일 이삼 이삼 반복" —
 * pattern twice, then 반복). Chosen 2026-09-21; see
 * docs/findings/17_repeating_decimals.md for the candidates it beat and for
 * the one case the choice leaves untested.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const sre = require('speech-rule-engine');
const temml = require('temml');
const { casualLatex, casualSpeech } = require('./casual');

// Same span grammar as normalize.py SPAN, restricted to the $-forms (this
// stage consumes normalize.py output, which only ever emits $..$ / $$..$$).
// Inline may not contain Hangul/'$'/newline so a stray '$' in prose can't
// swallow text. JS cannot share Python's regex, so this copy is held in sync
// by the shared fixtures in ../eval/fixtures/span_cases.json — span.test.js
// here and tests/test_span_grammar.py both check their regex against it.
const SPAN = /\$\$.+?\$\$|\$[^$\n가-힣]+?\$/gs;

const DEFAULT_COMBOS = [
  { domain: 'clearspeak', style: 'default' },
  { domain: 'mathspeak', style: 'default' },
];

const HR = '='.repeat(78);
const hr = '-'.repeat(78);

function parseArgs(argv) {
  const files = [];
  let combos = DEFAULT_COMBOS;
  let ssml = false;
  let both = false;
  let voice = 'ko-KR-SunHiNeural';
  let write = null;
  let strict = false;
  let altVoice = null;
  let casual = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--ssml') {
      ssml = true;
    } else if (a === '--both') {
      both = true;
    } else if (a === '--strict') {
      strict = true;
    } else if (a === '--casual') {
      casual = true;
    } else if (a === '--voice') {
      voice = argv[++i] ?? voice;
    } else if (a === '--alt-voice') {
      altVoice = argv[++i] ?? altVoice;
    } else if (a === '--write') {
      write = argv[++i] ?? '.';
    } else if (a === '--dir') {
      const dir = argv[++i] ?? '.';
      const found = fs
        .readdirSync(dir)
        .filter((f) => f.endsWith('.norm.md'))
        .sort()
        .map((f) => path.join(dir, f));
      if (!found.length) console.error(`(no *.norm.md files in ${dir})`);
      files.push(...found);
    } else if (a === '--combos') {
      combos = (argv[++i] ?? '').split(',').map((c) => {
        const [domain, style = 'default'] = c.trim().split('/');
        return { domain, style };
      });
    } else {
      files.push(a);
    }
  }
  if (!files.length) {
    console.error(
      'usage: node speak.js <file.norm.md ...> | --dir FOLDER [--combos d/s,d/s] [--ssml | --both] [--voice NAME] [--alt-voice NAME] [--write DIR] [--strict] [--casual]'
    );
    process.exit(1);
  }
  // radicand voice defaults to the opposite gender of the main voice
  altVoice ??= voice.includes('InJoon') ? 'ko-KR-SunHiNeural' : 'ko-KR-InJoonNeural';
  return { files, combos, ssml, both, voice, altVoice, write, strict, casual };
}

/* ----------------------------- SSML helpers ----------------------------- */

const escapeXml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** SRE SSML -> inner markup only (drop its <speak>/<prosody> envelope).
 * Also normalizes SRE's interpret-as="character" to Azure's "characters":
 * Azure's say-as table (learn.microsoft.com SSML pronunciation page, dated
 * 2026-02, checked 2026-08) lists only "characters"/"spell-out" — the
 * singular form is not a documented value, so Azure would silently ignore
 * the tag and the disambiguation the SSML path exists for would be lost. */
function ssmlInner(s) {
  const pros = s.match(/<prosody[^>]*>([\s\S]*)<\/prosody>/);
  const inner = pros ? pros[1] : (s.match(/<speak[^>]*>([\s\S]*)<\/speak>/) ?? [, s])[1];
  return capRate(inner).replace(/interpret-as="character"/g, 'interpret-as="characters"').trim();
}

/** Never faster than the voice's own pace. SRE wraps implied products ("3x",
 * "ab") in <prosody rate="+25%">; on Azure that rushes exactly the part a
 * listener needs most, and short answer choices that are all such terms fly
 * by (heard 2026-11-10). A <prosody> that speeds up is unwrapped, its content
 * kept; one that slows down or sets something else stays. */
function capRate(s) {
  const kept = []; // per open <prosody>: is its tag kept?
  return s.replace(/<prosody\b([^>]*)>|<\/prosody>/g, (tag, attrs) => {
    if (attrs === undefined) return kept.pop() === false ? '' : tag;
    const faster = /\brate="(\+(?!0+(\.0+)?%)[\d.]+%|x?-?fast)"/.test(attrs);
    kept.push(!faster);
    return faster ? '' : tag;
  });
}

// Label characters and blanks the Azure voice passes over in silence (measured
// 2026-11-10: "① 1" is exactly as long as "1", and "①" alone is no audio at
// all), so a listener never heard which answer choice was which. Each is given
// the words a person says for it with <sub alias>; the character stays in the
// text. A numbered choice also gets a pause before it and a short one after
// its number, so "① … ② … ③ …" is heard as separate choices, not one run.
const JAMO_KO = ['기역', '니은', '디귿', '리을', '미음', '비읍', '시옷', '이응', '지읒', '치읓', '키읔', '티읕', '피읖', '히읗'];
const GANA_KO = [...'가나다라마바사아자차카타파하'];
// Spelled out, not "2번": Azure reads a digit before 번 as a count ("두 번",
// twice), where a choice number is 이 번.
const SINO_KO = ['일', '이', '삼', '사', '오', '육', '칠', '팔', '구', '십', '십일', '십이', '십삼',
  '십사', '십오', '십육', '십칠', '십팔', '십구', '이십'];
const SILENT_MARK = new RegExp([
  '[\\u2460-\\u2473]',            // ① … ⑳
  '[\\u2474-\\u2487]',            // ⑴ … ⒇
  '[\\u3260-\\u327b]',            // ㉠ … ㉭, ㉮ … ㉻
  '[\\u3200-\\u321b]',            // ㈀ … ㈍, ㈎ … ㈛
  '[\\u24d0-\\u24e9]',            // ⓐ … ⓩ
  '[○◯□]',                        // a blank to fill in, drawn as a shape
  '\\(\\s+\\)|_{3,}',               // a blank written "(   )" or "____"
].join('|'), 'g');

// A number in a formula is always read 일, 이, 삼 …, but given the digit the
// Azure voice picks by what follows: "4 마이너스 2 i" came out "네 마이너스 이
// 아이" and "2 마이너스 i" "두 마이너스 아이", next to "육 플러스 사 아이" in the
// same problem (transcribed back from the audio, 2026-11-11). So the SSML
// carries the reading itself. The displayed text keeps its digits.
const digitsKo = (d) => [...d].map((c) => DIGIT_KO[c]).join(' ');

/** "24" -> "이십사", "3.14" -> "삼 점 일 사", "1,200" -> "천이백". */
function sinoKorean(num) {
  const [int, frac] = num.replace(/,/g, '').split('.');
  const whole = (int.length > 1 && int[0] === '0') || int.length > 16
    ? digitsKo(int)                           // "007", or too long to name
    : numberKo(int);
  return frac === undefined ? whole : `${whole} 점 ${digitsKo(frac)}`;
}

/** Math speech (SSML or plain) -> the same with every number spelled out.
 * Tags are skipped (break times, rates), and so is a number with Hangul
 * right after it ("3개" from a \text): that one is a count. */
const NUMBER_OR_TAG = /<[^>]*>|\d+(?:,\d{3})+(?:\.\d+)?(?![가-힣\d])|\d+(?:\.\d+)?(?![가-힣\d.])/g;
const spellNumbers = (s) => s.replace(NUMBER_OR_TAG, (m) => (m[0] === '<' ? m : sinoKorean(m)));

// The value after a choice number, when it is a bare number in the prose
// ("① 0 ② 2"): math too, so it is spelled the same way.
const CHOICE_VALUE = /(<sub alias="[^"]*">[\u2460-\u2473]<\/sub><break time="250ms"\/>[ \t]*)(\d+(?:\.\d+)?)(?=[ \t]*(?:<|\n|$))/g;

function spokenMark(m) {
  const c = m.codePointAt(0);
  const between = (lo, hi) => c >= lo && c <= hi;
  if (between(0x2460, 0x2473)) return `${SINO_KO[c - 0x2460]}번`;
  if (between(0x2474, 0x2487)) return `${SINO_KO[c - 0x2474]}번`;
  if (between(0x3260, 0x326d)) return JAMO_KO[c - 0x3260];
  if (between(0x326e, 0x327b)) return GANA_KO[c - 0x326e];
  if (between(0x3200, 0x320d)) return JAMO_KO[c - 0x3200];
  if (between(0x320e, 0x321b)) return GANA_KO[c - 0x320e];
  if (between(0x24d0, 0x24e9)) return String.fromCharCode(0x61 + c - 0x24d0);
  if (m === '○' || m === '◯') return '동그라미';
  if (m === '□') return '네모';
  return '빈칸';
}

/** Escaped text or assembled SSML body -> the same, with every silent mark
 * given its spoken words. Only text is touched: none of these characters can
 * occur inside a tag this file writes. */
// "①을 ②에 대입하면": a number referred to inside a sentence, not a choice
// being listed — no pauses around it.
const PARTICLE_NEXT = /^(?:에서|으로|을|를|이|가|은|는|에|의|와|과|로|도|만)(?![가-힣])/;
const speakMarks = (ssmlBody) => ssmlBody.replace(SILENT_MARK, (m, at) => {
  const sub = `<sub alias="${spokenMark(m)}">${m}</sub>`;
  const choice = m.length === 1 && m >= '\u2460' && m <= '\u2473'
    && !PARTICLE_NEXT.test(ssmlBody.slice(at + 1, at + 4));
  return choice ? `<break time="500ms"/>${sub}<break time="250ms"/>` : sub;
});

const AZURE_SSML = (voice, body) =>
  '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ko-KR">' +
  `<voice name="${voice}">${body}</voice></speak>`;

/* --------------------- repeating decimals (순환소수) --------------------- */

// #17, decided 2026-09-21: repeating decimals speak as reading C from the
// dot_reading_probe.py experiment — pattern twice, then 반복:
//   0.\dot{2}\dot{4}   -> "영 점 이사 이사 반복"
//   0.1\dot{2}\dot{3}  -> "영 점 일 이삼 이삼 반복"
// Known limit of this reading: on a PARTIAL repetend it separates 0.12̇3̇ from
// 0.1̇23̇ by phrasing alone ("일 이삼 이삼" vs "일이삼 일이삼"), which a TTS
// voice may flatten — the probe's case3-vs-case5 pair. Reading B marks the
// boundary with a word instead; swapping readRepeating() is the whole change.

const DIGIT_KO = { 0: '영', 1: '일', 2: '이', 3: '삼', 4: '사',
                   5: '오', 6: '육', 7: '칠', 8: '팔', 9: '구' };
const wordsKo = (digits) => [...digits].map((d) => DIGIT_KO[d]).join('');

/** Integer digits as a sino-Korean NUMBER, the way the integer part of a
 * decimal is read: "12" -> "십이", "105" -> "백오", "10000" -> "만". */
function numberKo(digits) {
  const n = digits.replace(/^0+(?=\d)/, '');
  if (n === '0') return '영';
  const PLACE = ['', '십', '백', '천'];
  const GROUP = ['', '만', '억', '조'];
  const groups = [];
  for (let end = n.length; end > 0; end -= 4) groups.unshift(n.slice(Math.max(0, end - 4), end));
  return groups.map((g, gi) => {
    const unit = GROUP[groups.length - 1 - gi];
    let out = '';
    [...g].forEach((d, i) => {
      if (d === '0') return;
      const place = PLACE[g.length - 1 - i];
      out += (d === '1' && place ? '' : DIGIT_KO[d]) + place;  // 십, not 일십
    });
    if (!out) return '';
    return (out === '일' && unit ? '' : out) + unit;           // 만, not 일만
  }).join('');
}

// dotted form 0.1\dot{2}\dot{3} (normalize.py's canonical output for 2̇) or
// overline form 1.\overline{23}
const REPDEC = /(\d+)\.((?:\d|\\dot\{\d\})*\\dot\{\d\}(?:\d|\\dot\{\d\})*|\d*\\overline\{\d+\})/g;

/** (integer digits, fractional latex) -> reading-C Korean text, or null when
 * the notation is invalid (digits after the last dot). The integer part is a
 * number ("십이 점 ..."); the digits after the point are read one by one. */
function readRepeating(intPart, fracRaw) {
  let pre;
  let rep;
  const over = fracRaw.match(/^(\d*)\\overline\{(\d+)\}$/);
  if (over) {
    [, pre, rep] = over;
  } else {
    const toks = [...fracRaw.matchAll(/\\dot\{(\d)\}|(\d)/g)]
      .map((m) => ({ d: m[1] ?? m[2], dotted: m[1] !== undefined }));
    const first = toks.findIndex((t) => t.dotted);
    const last = toks.length - 1 - [...toks].reverse().findIndex((t) => t.dotted);
    if (last !== toks.length - 1) return null; // trailing undotted digits: not valid notation
    pre = toks.slice(0, first).map((t) => t.d).join('');
    rep = toks.slice(first).map((t) => t.d).join('');
  }
  const r = wordsKo(rep);
  return `${numberKo(intPart)} 점${pre ? ` ${wordsKo(pre)}` : ''} ${r} ${r} 반복`;
}

/** Split a span's LaTeX at repeating decimals: [{latex}|{text}, ...] where
 * {text} is ready-made Korean prose that bypasses temml/SRE entirely. */
function splitRepeating(latex) {
  const segs = [];
  let last = 0;
  for (const m of latex.matchAll(REPDEC)) {
    const text = readRepeating(m[1], m[2]);
    if (text === null) continue;
    const before = latex.slice(last, m.index);
    if (before.trim()) segs.push({ latex: before });
    segs.push({ text });
    last = m.index + m[0].length;
  }
  if (!segs.length) return [{ latex }];
  const after = latex.slice(last);
  if (after.trim()) segs.push({ latex: after });
  return segs;
}

/* ------------------------- 선분 (\overline over letters) ------------------ */

// \overline over LETTERS is 선분 (line segment), not a decoration. SRE reads it
// as "A B 윗줄" — it names the bar and never says the word, 21 times in the
// current corpus (#20, ❌ list). Intercepted here rather than rewritten after
// SRE because the fix is a REORDER — Korean puts 선분 FIRST — and in the SSML
// path the letters sit inside <say-as> tags, so a regex moving the word would
// have to cross markup.
// \overrightarrow and \vec name the bar the same way and are deliberately left
// alone: the same notation is 반직선 in 중1 and 벡터 in 고등, so it needs a
// reading decision, not a rewrite.
const SEGMENT = /\\overline\{([A-Z]{2,4})\}/g;

function splitSegments(latex) {
  const segs = [];
  let last = 0;
  for (const m of latex.matchAll(SEGMENT)) {
    const before = latex.slice(last, m.index);
    if (before.trim()) segs.push({ latex: before });
    segs.push({ text: `선분 ${[...m[1]].join(' ')}` });
    last = m.index + m[0].length;
  }
  if (!segs.length) return [{ latex }];
  const after = latex.slice(last);
  if (after.trim()) segs.push({ latex: after });
  return segs;
}

/* ------------- 순서쌍/구간 fences, and ⊥ word order (#20, ⚠ list) --------- */

// SRE-ko drops the fence around a NUMERIC tuple — "(3,4)" and "(-2,5)" both
// speak as bare "3 콤마 4" — while keeping it for a symbolic one, "(a,b)" ->
// "괄호 열고 a 콤마 b 괄호 닫고". So (3,4), [3,4] and a bare 3,4 are all the
// same sound, and the corpus has 50 real coordinate pairs plus one problem
// whose whole point is telling a 자릿점 comma from a 순서쌍 comma. Speaking
// the fence makes the numeric case consistent with the symbolic one.
const TUPLE = /([([])\s*(-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)+)\s*([)\]])/g;
const FENCE = { '(': ['괄호 열고', '괄호 닫고'], '[': ['대괄호 열고', '대괄호 닫고'] };
const MATCHING = { '(': ')', '[': ']' };

// SRE-ko renders a binary \perp with no particles at all — "l 수직이다 m" —
// though it gets \parallel right ("l 은 m 과 평행하다"). The words have to
// MOVE, so this is interception rather than a post-SRE rewrite. The particle
// follows the 받침 of the letter's KOREAN pronunciation, not its spelling, and
// only the LAST syllable counts: l is 엘 (받침 -> 은/과) but x is 엑스, ending
// in 스 with none -> 는/와. SRE's own binary readings corroborate the set
// ("x 는 3 보다", "s 는 3 보다", "f 는 3 보다"); an earlier version of this list
// wrongly included f/s/x by reading their spelling rather than their sound.
// r is 알 and takes 은 — SRE says "r 은 3" too.
const BATCHIM = new Set(['l', 'm', 'n', 'r']);
const PERP = /([A-Za-z])\s*\\perp\s*([A-Za-z])(?![A-Za-z])/g;
const hasBatchim = (w) => BATCHIM.has(w[w.length - 1].toLowerCase());

// 받침 of an actual Hangul syllable (for particles chosen across a split):
// (code - 0xAC00) % 28 is the final-consonant index, 0 meaning none.
const lastHangul = (s) => {
  const m = s.replace(/<[^>]*>/g, '').match(/[가-힣](?=[^가-힣]*$)/);
  return m ? m[0] : '';
};
const hasJong = (ch) => (ch.charCodeAt(0) - 0xac00) % 28 !== 0;

// Whether the last SPOKEN word ends in a 받침 — a trailing digit or letter is
// read aloud too, so "루트 x 더하기 1" ends in 일 (은), not in 기 from 더하기.
// Digits: 영 일 삼 육 칠 팔 have one, and a trailing 0 is 영/십/백/천/만.
// null when nothing tells (no Hangul, digit or letter at the end).
function endsWithJong(s) {
  const t = s.replace(/<[^>]*>|[\x01\x02]/g, ' ').trimEnd();  // markup, voice markers
  const c = t[t.length - 1] ?? '';
  if (/[0-9]/.test(c)) return '013678'.includes(c);
  if (/[A-Za-z]/.test(c)) return BATCHIM.has(c.toLowerCase());
  if (/[가-힣]/.test(c)) return hasJong(c);
  const h = lastHangul(t);
  return h ? hasJong(h) : null;
}

// A CHAIN of relations loses every particle: SRE reads "x \\leq 3" correctly as
// "x 는 3 보다 작거나 같다" but "p \\leq k < q" as a bare "p 작거나 같다 k 작다
// q". Splitting the chain into its overlapping binary pairs gets the particles
// back from SRE itself, so no 받침 table is involved — the pivot is simply
// spoken twice, which is how the relation is read aloud anyway.
const RELS = String.raw`\\(?:leq|geq|le|ge|lt|gt)(?![A-Za-z])|<|>`;
// a term may carry a superscript ("x^2 < y < z"); the lookbehind stops the
// match starting INSIDE one, which used to slice "x^2" into "x^" + "2".
// Besides plain letters/digits, a term may be a fraction, a root, a Greek
// letter or an absolute value — "0 < x < \\pi", "\\frac{1}{2} < x < \\frac{3}{2}"
// and "3 < |x-1| < 5" are as common as "1 < x < 3" (braces: one nesting level).
const BRACED = String.raw`\{(?:[^{}]|\{[^{}]*\})*\}`;
const ATOM = String.raw`(?:\\frac(?:${BRACED}${BRACED}|\d\d)|\\sqrt(?:\[[^\]]*\])?${BRACED}`
  + String.raw`|\\(?:pi|alpha|beta|theta|infty)(?![A-Za-z])|\|[^|<>=]+\||[A-Za-z0-9.]+)`;
const TERM = String.raw`-?${ATOM}(?:\^\{?[A-Za-z0-9]+\}?)?`;
const CHAIN = new RegExp(
  String.raw`(?<![A-Za-z0-9.^_{\\])` + `${TERM}(?:\\s*(?:${RELS})\\s*${TERM}){2,}`, 'g');
const CHAIN_TOKEN = new RegExp(`${RELS}|${TERM}`, 'g');

function splitChains(latex) {
  const segs = [];
  let last = 0;
  for (const m of latex.matchAll(CHAIN)) {
    // the whole chain is consumed, however many links: a 3-relation chain used
    // to leave a dangling " \leq r" that spoke as a clause with no subject
    const tok = m[0].match(CHAIN_TOKEN);
    if (!tok || tok.length < 5 || tok.length % 2 === 0) continue;
    const before = latex.slice(last, m.index);
    if (before.trim()) segs.push({ latex: before });
    for (let i = 0; i + 2 < tok.length; i += 2) {
      if (i) segs.push({ text: ',' });
      // spaces matter: "p\\leqk" is an unknown command to temml
      segs.push({ latex: `${tok[i]} ${tok[i + 1]} ${tok[i + 2]}` });
    }
    last = m.index + m[0].length;
  }
  if (!segs.length) return [{ latex }];
  const after = latex.slice(last);
  if (after.trim()) segs.push({ latex: after });
  return segs;
}

// |x-2| reads "절댓값 x 빼기 2", so "|x-2|+3" becomes "절댓값 x 빼기 2 더하기 3"
// — indistinguishable from |x-2+3| (#20, ⚠ list). Korean prints the marker
// AFTER the operand, which scopes on its own: "x 빼기 2 의 절댓값 더하기 3".
// Only a COMPLEX operand moves; "절댓값 마이너스 4" for |-4| is already complete
// and unambiguous, and inbox_eval.py's judge prompt asserts exactly that.
const ABS = /\|([^|]+)\|/g;
const SIMPLE_OPERAND = /^\s*-?[A-Za-z0-9.]+\s*$/;
// Right after a relation the move would strand it: "3 < |x-1|" spoke as
// "3 은 보다 작다 x 빼기 1 의 절댓값" — Korean puts the verb LAST, so the
// relation needs its object inside the same SRE fragment. The prefix reading
// ("3 은 절댓값 x 빼기 1 보다 작다") is complete there, the verb closes it.
const ENDS_REL = new RegExp(`(?:${RELS})\\s*$`);
// "2|x-1|": a coefficient glued to the bars. With 절댓값 moved after the
// operand, it would sound exactly like |2x-1| ("2 x 빼기 1 의 절댓값").
const ENDS_OPERAND = /[A-Za-z0-9.)}]\s*$/;

function splitAbs(latex) {
  const segs = [];
  let last = 0;
  for (const m of latex.matchAll(ABS)) {
    if (SIMPLE_OPERAND.test(m[1])) continue;   // prefix reading is already fine
    if (ENDS_REL.test(latex.slice(0, m.index))) continue;
    const before = latex.slice(last, m.index);
    if (before.trim()) segs.push({ latex: before });
    if (ENDS_OPERAND.test(before)) segs.push({ text: '곱하기' });
    segs.push({ latex: m[1] }, { text: '의 절댓값' });
    last = m.index + m[0].length;
  }
  if (!segs.length) return [{ latex }];
  const after = latex.slice(last);
  if (after.trim()) segs.push({ latex: after });
  return segs;
}

function splitFences(latex) {
  const segs = [];
  let last = 0;
  const push = (end, text) => {
    const before = latex.slice(last, end);
    if (before.trim()) segs.push({ latex: before });
    segs.push({ text });
  };
  for (const m of [...latex.matchAll(TUPLE), ...latex.matchAll(PERP)]
                  .sort((a, b) => a.index - b.index)) {
    if (m.index < last) continue;                 // overlapping match already used
    if (m[3] !== undefined) {                     // TUPLE
      if (m[3] !== MATCHING[m[1]]) continue;      // mismatched pair: leave it
      const [open, close] = FENCE[m[1]];
      const nums = m[2].split(',')
        .map((n) => n.trim().replace(/^-/, '마이너스 '))
        .join(' 콤마 ');
      push(m.index, `${open} ${nums} ${close}`);
    } else {                                      // PERP
      push(m.index, `${m[1]} ${hasBatchim(m[1]) ? '은' : '는'} `
                  + `${m[2]} ${hasBatchim(m[2]) ? '과' : '와'} 수직이다`);
    }
    last = m.index + m[0].length;
  }
  if (!segs.length) return [{ latex }];
  const after = latex.slice(last);
  if (after.trim()) segs.push({ latex: after });
  return segs;
}

// A fragment ending in a SIGN minus ("y=-" before |x-1|, a lone "-" before
// 0.\dot{3} or a radical) is spoken by SRE as a dangling "빼기". The sign
// belongs to what follows, so it becomes its own word.
const SIGN_TAIL = /^(.*?)\s*-\s*$/s;
const SIGN_CONTEXT = /(?:^|[=<>(\[{,]|\\(?:leq|geq|le|ge|lt|gt|neq|ne)(?![A-Za-z]))\s*$/;
const SIGN = { text: '마이너스', sign: true };

function splitSignTails(segs) {
  const out = [];
  segs.forEach((seg, i) => {
    const m = seg.latex !== undefined && i + 1 < segs.length && seg.latex.match(SIGN_TAIL);
    // a fragment that is ONLY the minus ("\\sqrt{a}-\\sqrt{b}" splits around
    // it) takes its context from the segment before
    if (m && (m[1].trim() ? SIGN_CONTEXT.test(m[1]) : !endsOnOperand(out[out.length - 1]))) {
      if (m[1].trim()) out.push({ latex: m[1] });
      out.push(SIGN);
    } else {
      out.push(seg);
    }
  });
  return out;
}

/** True when `prev` (the segment before a fragment starting with +/-) ends on
 * an operand, so that sign is a binary operator: "\sqrt{a+b}+1", "|x-2|-3".
 * After nothing, a chain's comma, a relation or an opening bracket it is a
 * sign: "-2 < x" is 마이너스 2, never 빼기 2. */
function endsOnOperand(prev) {
  if (!prev) return false;
  if (prev.root !== undefined) return true;
  if (prev.text !== undefined) return !(prev.sign || prev.text === ',' || prev.text === '곱하기');
  return !/(?:[=<>(\[{,+\-]|\\(?:leq|geq|le|ge|lt|gt|neq|ne|pm|times|div|cdot)(?![A-Za-z]))\s*$/
    .test(prev.latex);
}

/** Repeating-decimal + 선분 + fence/⊥ splits (both modes); radicals SSML only. */
function splitSpecials(latex, withRadicals) {
  return splitSignTails(splitSpecialsRaw(latex, withRadicals));
}

function splitSpecialsRaw(latex, withRadicals) {
  const out = [];
  for (const seg of splitRepeating(latex)) {
    if (seg.latex === undefined) {
      out.push(seg);
      continue;
    }
    for (const seg2 of splitSegments(seg.latex)) {
      if (seg2.latex === undefined) {
        out.push(seg2);
        continue;
      }
      for (const seg3 of splitFences(seg2.latex)) {
        if (seg3.latex === undefined) { out.push(seg3); continue; }
        for (const seg4 of splitChains(seg3.latex)) {
          if (seg4.latex === undefined) { out.push(seg4); continue; }
          for (const sub of splitAbs(seg4.latex)) {
            if (sub.latex !== undefined && withRadicals) out.push(...splitRadicals(sub.latex));
            else out.push(sub);
          }
        }
      }
    }
  }
  return out;
}

/* --------------------- radical grouping by voice change ------------------ */

// a radicand worth marking: contains an operator or a nested structure, i.e.
// the "where does the root end?" ambiguity actually exists. \sqrt{2}, \sqrt{ab}
// stay whole-span.
const COMPLEX_RADICAND = /[+\-±×÷]|\\(?:frac|sqrt|pm|times|div|cdot)\b/;

const parenBalanced = (s) => {
  let d = 0;
  for (const c of s) {
    if (c === '(') d++;
    else if (c === ')' && --d < 0) return false;
  }
  return d === 0;
};

/**
 * Split a span's LaTeX at top-level complex radicals so the SSML stitcher can
 * speak each radicand in the alternate-gender voice: the voice change marks
 * where the root starts and ends, replacing spoken grouping parentheses
 * (a paren pair wrapping the whole radicand is dropped for the same reason).
 * Returns [{latex}|{root}, ...]; a single {latex} segment means nothing to do.
 * Only the OUTERMOST complex radical splits — a nested radical stays inside
 * its parent's segment, so voices don't ping-pong mid-expression.
 */
function splitRadicals(latex) {
  const segs = [];
  let plain = '';
  let i = 0;
  while (i < latex.length) {
    if (latex.startsWith('\\sqrt', i) && !/[a-zA-Z]/.test(latex[i + 5] ?? '')) {
      let j = i + 5;
      while (latex[j] === ' ') j++;
      if (latex[j] === '{') {
        let depth = 1;
        let k = j + 1;
        while (k < latex.length && depth) {
          if (latex[k] === '{') depth++;
          else if (latex[k] === '}') depth--;
          k++;
        }
        let inner = latex.slice(j + 1, k - 1);
        if (!depth && COMPLEX_RADICAND.test(inner)) {
          const m = inner.match(/^\((.*)\)$/s);
          if (m && parenBalanced(m[1])) inner = m[1]; // 괄호 words -> voice change
          if (plain.trim()) segs.push({ latex: plain });
          plain = '';
          segs.push({ root: inner });
          i = k;
          continue;
        }
      }
    }
    plain += latex[i++];
  }
  if (plain.trim()) segs.push({ latex: plain });
  return segs;
}

/**
 * Well-formedness check for the assembled SSML (issue #11). The Azure envelope
 * is built by string-joining regex-extracted markup, and nothing downstream
 * parses it until Azure does — so a stray '<', an unclosed tag or bad nesting
 * would only surface as a synthesis error in stage 4. Catch it here instead.
 * Returns null if well-formed, else a short error string.
 */
function checkWellFormed(xml) {
  // sticky (/y) so each token is matched in place — no per-token slicing
  const ENTITY = /&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);/y;
  const TAG = /<(\/)?([A-Za-z_][A-Za-z0-9._:-]*)((?:\s+[A-Za-z_][A-Za-z0-9._:-]*\s*=\s*(?:"[^"<]*"|'[^'<]*'))*)\s*(\/)?>/y;
  const stack = [];
  let i = 0;
  while (i < xml.length) {
    const ch = xml[i];
    if (ch === '<') {
      TAG.lastIndex = i;
      const m = TAG.exec(xml);
      if (!m) return `unparseable tag at offset ${i}: ${JSON.stringify(xml.slice(i, i + 40))}`;
      const [whole, closing, name, , selfClosing] = m;
      if (closing) {
        if (stack[stack.length - 1] !== name)
          return `</${name}> closes <${stack[stack.length - 1] ?? '(nothing)'}>`;
        stack.pop();
      } else if (!selfClosing) {
        stack.push(name);
      }
      i += whole.length;
    } else if (ch === '&') {
      ENTITY.lastIndex = i;
      const m = ENTITY.exec(xml);
      if (!m) return `bare '&' at offset ${i}: ${JSON.stringify(xml.slice(i, i + 20))}`;
      i += m[0].length;
    } else if (ch === '>') {
      return `stray '>' at offset ${i}`;
    } else {
      i++;
    }
  }
  return stack.length ? `unclosed <${stack[stack.length - 1]}>` : null;
}

/**
 * Post-SRE speech rewrites for SRE-ko misreads with a known better Korean form.
 * Each pattern stays inside ONE text node, so the SSML path's <say-as> tags
 * around identifiers are never split by a rewrite.
 *
 *  - \Box (fill-in-the-blank □) is read "흰색 정사각형" (lit. "white square");
 *    Korean math speech calls the blank "네모".
 *  - a squared/cubed unit comes out in English order ("센티미터 제곱"); Korean
 *    puts the exponent FIRST (제곱센티미터). normalize.py wraps every metric
 *    unit in \mathrm{}, so this reaches all of them (issue #20, ⚠ list).
 *  - "흰색 상향 삼각형" is the Unicode name of △ leaking through; the word is
 *    just 삼각형. ∽ is read "역 물결표"; in this pipeline it only ever means
 *    닮음, so it reads 닮음이다 (both #20, ❌ list). normalize.py writes ∽ as
 *    \sim, which SRE reads "물결표" exactly like the accent \tilde{x} ("x 물결표
 *    더하기 1"), so similarLatex() turns \sim into \backsim before SRE and only
 *    "역 물결표" becomes 닮음이다.
 *  - SRE spells the trig functions 싸인/코싸인; textbooks write 사인/코사인.
 *  - a ratio colon is read "콜론"; 비례식 is spoken "대" — 3:4 is "삼 대 사", not
 *    "삼 콜론 사" (issue #20, ❌ list). Chains fall out for free: the matches
 *    do not overlap, so "3 콜론 4 콜론 5" becomes "3 대 4 대 5". A colon in
 *    고등학교 set-builder notation would also be caught, but none reaches this
 *    pipeline — every ':' in 초·중 print is a ratio.
 */
// \sim is the 닮음 sign here (see the note above): give it its own symbol, ∽,
// so its reading cannot be confused with the \tilde accent.
const similarLatex = (latex) => latex.replace(/\\sim(?![A-Za-z])/g, '\\backsim ');

const UNIT_POWER = /(센티미터|밀리미터|킬로미터|미터) (세제곱|제곱)/g;

const ROW_ORDINAL = ['첫째', '둘째', '셋째', '넷째', '다섯째'];

function fixMisreads(speech) {
  return speech
    .replace(/흰색 정사각형/g, '네모')
    .replace(/흰색 상향 삼각형/g, '삼각형')   // Unicode character name leaking
    .replace(/역 물결표/g, '닮음이다')         // ∽ (see note); a plain 물결표 is \tilde
    .replace(/코싸인/g, '코사인')              // textbook spelling (#20)
    .replace(/싸인/g, '사인')
    .replace(UNIT_POWER, '$2$1')
    .replace(/(^|\s)콜론(?=\s|$)/g, '$1대')    // also a ':' rendered on its own
    // A brace over several rows (연립방정식, a piecewise function) comes out as
    // "총 케이스 수 2 케이스 1: … 케이스 2: …"; say 첫째, … 둘째, … instead.
    .replace(/총 케이스 수 \d+\s*(?:<break[^>]*\/>\s*)?/g, '')
    .replace(/케이스 (\d+):/g, (_, n) => `${ROW_ORDINAL[n - 1] ?? `${n}번째`},`);
}

/**
 * Best-effort reading for LaTeX temml cannot parse (broken OCR output).
 * Keeps the human-readable content (\text bodies, numbers, operators) and
 * drops commands/braces — NEVER let a ParseError message reach the speech.
 */
const SALVAGE_KO = {
  pm: '플러스 마이너스', sqrt: '루트', times: '곱하기', div: '나누기',
  cdot: '곱하기', frac: '분수', pi: '파이', infty: '무한대',
  sin: '사인', cos: '코사인', tan: '탄젠트', leq: '작거나 같다', geq: '크거나 같다',
};

function salvage(latex) {
  return latex
    .replace(/\\text\s*\{([^{}]*)\}/g, ' $1 ')
    .replace(/\\([a-zA-Z]+)\*?/g, (m, c) => (SALVAGE_KO[c] ? ` ${SALVAGE_KO[c]} ` : ' '))
    .replace(/[\\{}$~&^_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Split text into alternating prose / math-span parts, keeping order.
 * \text{..} bodies are masked first so a genuine math span whose only Hangul
 * lives in \text arguments (normalize.py preserves those) still matches SPAN's
 * no-Hangul rule, then restored so temml/SRE see the real content. */
function splitSpans(text) {
  const bodies = [];
  const masked = text.replace(/\\text\s*\{([^{}]*)\}/g, (_, b) => {
    bodies.push(b);
    return `\\text{\x00${bodies.length - 1}\x00}`;
  });
  const unmask = (s) => s.replace(/\x00(\d+)\x00/g, (_, i) => bodies[+i]);
  const parts = []; // {prose} | {latex}
  let last = 0;
  for (const m of masked.matchAll(SPAN)) {
    if (m.index > last) parts.push({ prose: unmask(masked.slice(last, m.index)) });
    const raw = m[0];
    const latex = raw.startsWith('$$') ? raw.slice(2, -2) : raw.slice(1, -1);
    // an empty "$ $" (stray-dollar pairing) is not math — keep it out of the
    // pipeline entirely or it would stitch as "[지원되지 않는 수식: ]"
    if (latex.trim()) parts.push({ latex: unmask(latex.trim()) });
    else parts.push({ prose: ' ' });
    last = m.index + raw.length;
  }
  if (last < masked.length) parts.push({ prose: unmask(masked.slice(last)) });
  return parts;
}

async function main() {
  const { files, combos, ssml: ssmlFlag, both, voice, altVoice, write, strict, casual } =
    parseArgs(process.argv.slice(2));
  // --casual (casual.js): simplified LaTeX in, shortened phrases out
  const spoken = casual ? casualSpeech : (s) => s;
  const modes = both ? [false, true] : [ssmlFlag];   // false = plain, true = SSML
  if (write) fs.mkdirSync(write, { recursive: true });
  const writeStitched = (file, content, ssml) => {
    if (!write) return;
    const base = path.basename(file).replace(/\.norm\.md$/, '');
    const dest = path.join(write, `${base}.stitched.${ssml ? 'ssml' : 'txt'}`);
    fs.writeFileSync(dest, content + '\n');
    console.log(`  -> wrote ${dest}`);
  };

  // Collect unique latex spans across all files first, then run combo-outer so
  // the (global) engine is set up once per combo instead of once per span.
  const docs = files.map((file) => {
    const text = fs.readFileSync(file, 'utf8').trim();
    const parts = splitSpans(text);
    for (const part of parts) {
      if (part.latex === undefined) continue;
      part.latex = similarLatex(part.latex);
      if (casual) part.latex = casualLatex(part.latex);
    }
    return { file, parts };
  });

  // Everything needing speech: each span whole, plus (SSML mode) its radical
  // segments — the whole span stays registered as the fallback if a segment
  // fails to convert.
  const wanted = new Set();
  for (const doc of docs) {
    for (const part of doc.parts) {
      if (part.latex === undefined) continue;
      wanted.add(part.latex);
      for (const ssml of modes) {
        for (const seg of splitSpecials(part.latex, ssml)) {
          if (seg.text === undefined) wanted.add(seg.root ?? seg.latex);
        }
      }
    }
  }

  const mathml = new Map(); // latex -> {mathml} | {error}
  for (const latex of wanted) {
    try {
      // throwOnError so broken LaTeX lands in the catch; belt-and-suspenders
      // <merror> check in case temml still renders an inline error message
      // (SRE would read it aloud: "백슬래시 ParseError 콜론 ...").
      const xml = temml.renderToString(latex, { xml: true, throwOnError: true });
      if (xml.includes('<merror')) throw new Error('temml emitted <merror>');
      mathml.set(latex, { mathml: xml });
    } catch (err) {
      mathml.set(latex, { error: String(err) });
    }
  }

  // Failure accounting (issue #11): a span that stitched as salvage or a
  // placeholder used to be one console line scrolling past while the run
  // still finished "successfully". Count per doc, summarize, and let
  // --strict turn any failure into a non-zero exit for wrapper scripts.
  const totals = { spans: 0, ok: 0, salvaged: 0, unsupported: 0, badXml: 0 };

  for (const ssml of modes) {
    // speech.get(latex).get('domain/style') -> string | {error}
    const speech = new Map([...mathml.keys()].map((l) => [l, new Map()]));
    for (const { domain, style } of combos) {
      await sre.setupEngine({
        locale: 'ko', domain, style, modality: 'speech', markup: ssml ? 'ssml' : 'none',
      });
      await sre.engineReady();
      for (const [latex, conv] of mathml) {
        const key = `${domain}/${style}`;
        if (conv.error) {
          speech.get(latex).set(key, { error: `MathML conversion failed: ${conv.error}` });
          continue;
        }
        try {
          speech.get(latex).set(key, fixMisreads(sre.toSpeech(conv.mathml)));
        } catch (err) {
          speech.get(latex).set(key, { error: String(err) });
        }
      }
    }

    // The stitched view uses the FIRST combo's speech.
    const stitchKey = `${combos[0].domain}/${combos[0].style}`;

    for (const doc of docs) {
      console.log();
      console.log(HR);
      console.log(doc.file);
      console.log(HR);

      const seen = new Set();
      for (const part of doc.parts) {
        if (part.latex === undefined || seen.has(part.latex)) continue;
        seen.add(part.latex);
        console.log(`  $${part.latex}$`);
        for (const [key, out] of speech.get(part.latex)) {
          const tag = key.padEnd(22);
          if (typeof out === 'string') {
            const flag = out.trim() ? '' : '  << EMPTY OUTPUT';
            console.log(`    ${tag} ${out}${flag}`);
          } else {
            console.log(`    ${tag} !! ${out.error}`);
          }
        }
      }

      // Render one span for the stitched view, recording how it went:
      // ok (real speech) / salvaged (best-effort words) / unsupported (placeholder).
      const stats = { spans: 0, ok: 0, salvaged: 0, unsupported: 0, badXml: 0 };
      const renderSpan = (latex, escape) => {
        stats.spans++;
        // Segment path: repeating decimals speak as ready-made Korean text in
        // BOTH modes (reading C, decided — see the #17 note above); a complex
        // radicand switches to the alternate-gender voice (SSML only). Any
        // segment without clean speech falls back to the whole-span path.
        const segs = splitSpecials(latex, ssml);
        if (segs.some((s) => s.text !== undefined || s.root !== undefined)) {
          const rendered = [];
          for (const [si, seg] of segs.entries()) {
            if (seg.text !== undefined) {
              rendered.push(` ${escape(seg.text)} `);
              continue;
            }
            let segOut = speech.get(seg.root ?? seg.latex)?.get(stitchKey);
            if (typeof segOut !== 'string' || !segOut.trim()) {
              rendered.length = 0;
              break;
            }
            // A trailing fragment like "+1" is rendered on its own, so SRE reads
            // its leading sign as UNARY — "루트 a 더하기 b 플러스 1" for
            // \sqrt{a+b}+1. Continuing an expression, it is binary; at the
            // start, after a chain's comma or after '=' it is still a sign.
            if (seg.latex !== undefined && /^\s*[+-]/.test(seg.latex) && endsOnOperand(segs[si - 1])) {
              segOut = segOut.replace(/^((?:\s|<[^>]*>)*)플러스/, '$1더하기')
                             .replace(/^((?:\s|<[^>]*>)*)마이너스/, '$1빼기');
            }
            // SRE picks the copula 는/은 for '=' from the fragment alone, so a
            // reordering split can leave it disagreeing with what now precedes
            // it ("...의 절댓값 는 5"). Re-pick it from the real 받침.
            if (rendered.length) {
              const jong = endsWithJong(rendered.join(''));
              if (jong !== null) {
                segOut = segOut.replace(/^((?:\s|<[^>]*>)*)(?:는|은)(?=\s)/,
                                        (_m, pre) => pre + (jong ? '은' : '는'));
              }
            }
            // \x01/\x02 mark the alt-voice region; Azure forbids a <voice>
            // inside a <voice>, so the envelope assembly turns the markers
            // into SIBLING voice elements instead of nesting them.
            rendered.push(seg.root !== undefined
              ? ` 루트 \x01${ssmlInner(segOut)}\x02 `
              : ssml ? ` ${ssmlInner(segOut)} ` : ` ${segOut.trim()} `);
          }
          if (rendered.length) {
            stats.ok++;
            // a 곱하기 put in by splitAbs is a real product: casual must keep it
            const keepTimes = /\\(?:times|cdot)/.test(latex) || segs.some((s) => s.text === '곱하기');
            return spoken(rendered.join(''), { keepTimes });
          }
        }
        const out = speech.get(latex).get(stitchKey);
        if (typeof out === 'string' && out.trim()) {
          stats.ok++;
          return spoken(ssml ? ` ${ssmlInner(out)} ` : ` ${out.trim()} `,
                        { keepTimes: /\\(?:times|cdot)/.test(latex) });
        }
        const saved = salvage(latex);
        if (saved) {
          stats.salvaged++;
          return ` ${escape(saved)} `;
        }
        stats.unsupported++;
        return ` [지원되지 않는 수식: ${escape(latex)}] `;
      };

      console.log(hr);
      if (ssml) {
        console.log(`STITCHED SSML (${stitchKey}, Azure envelope, voice=${voice}):`);
        console.log(hr);
        const joined = doc.parts
          .map((part) =>
            part.latex === undefined ? escapeXml(part.prose) : spellNumbers(renderSpan(part.latex, escapeXml))
          )
          .join('')
          .replace(/ +/g, ' ')
          .trim();
        // math speech included: a label inside a span ("… ⋯ ㉠") is as silent
        const body = speakMarks(joined)
          .replace(CHOICE_VALUE, (_m, lead, n) => lead + sinoKorean(n))
          // alt-voice markers -> sibling <voice> elements (nesting is rejected
          // by Azure: "[voice] should not contain [voice]")
          .replaceAll('\x01', `</voice><voice name="${altVoice}">`)
          .replaceAll('\x02', `</voice><voice name="${voice}">`);
        const doc_ssml = AZURE_SSML(voice, body)
          .replace(/<voice name="[^"]*">\s*<\/voice>/g, ''); // drop empty runs
        console.log(doc_ssml);
        const xmlErr = checkWellFormed(doc_ssml);
        if (xmlErr) {
          stats.badXml++;
          console.error(`  !! SSML NOT WELL-FORMED (${xmlErr}) — not writing this file`);
        } else {
          writeStitched(doc.file, doc_ssml, ssml);
        }
      } else {
        console.log(`STITCHED (${stitchKey}) — what a TTS voice would read:`);
        console.log(hr);
        const stitched = doc.parts
          .map((part) =>
            part.latex === undefined ? part.prose : renderSpan(part.latex, (s) => s)
          )
          .join('')
          .replace(/ +/g, ' ')
          .trim();
        console.log(stitched);
        writeStitched(doc.file, stitched, ssml);
      }

      // Same shape as stage 1's eval summary: one scannable line per doc.
      const flags = [
        stats.salvaged && `salvaged: ${stats.salvaged}`,
        stats.unsupported && `UNSUPPORTED (placeholder in output): ${stats.unsupported}`,
        stats.badXml && 'SSML MALFORMED',
      ].filter(Boolean);
      console.log(`${both && ssml ? '(ssml) ' : ''}SUMMARY: ${stats.spans} span(s), ok: ${stats.ok}` +
        (flags.length ? `   ${flags.join('   ')}` : ''));
      for (const k of Object.keys(totals)) totals[k] += stats[k];
    }
  }

  const failures = totals.salvaged + totals.unsupported + totals.badXml;
  if (failures) {
    console.error(`\n${failures} span(s)/doc(s) FAILED across ${docs.length} file(s) ` +
      `(salvaged: ${totals.salvaged}, unsupported: ${totals.unsupported}, malformed SSML: ${totals.badXml}).`);
    if (strict) process.exitCode = 2;
    else console.error('(exit 0 without --strict; pass --strict to fail the run on this)');
  }
}

module.exports = { SPAN, checkWellFormed, splitRadicals, splitRepeating, splitSegments,
                   splitFences, splitChains, splitAbs, splitSpecials, endsWithJong,
                   fixMisreads, capRate, speakMarks, sinoKorean, spellNumbers };

if (require.main === module) {
  main().catch((err) => {
    console.error('FATAL:', err);
    process.exit(1);
  });
}
