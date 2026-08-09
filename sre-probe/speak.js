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
 *
 * Default combos: clearspeak/default (natural register, used for the stitched
 * view) and mathspeak/default (unambiguous register), per the index.js probe.
 *
 * --ssml: SRE emits SSML per span (its own structural <break>s + <say-as> around
 * identifiers). SRE's envelope is <speak version="1.1" xml:lang="ko"> with no
 * <voice>, which Azure rejects — so the stitched view strips each span down to
 * its inner markup and re-wraps the whole document in the Azure envelope
 * (version="1.0", xml:lang="ko-KR", <voice name=...>). Prose is XML-escaped.
 * Caveat: SRE writes interpret-as="character"; Azure documents "characters" —
 * verify by ear with tts_probe.py before trusting the say-as tags.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const sre = require('speech-rule-engine');
const temml = require('temml');

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
  let voice = 'ko-KR-SunHiNeural';
  let write = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--ssml') {
      ssml = true;
    } else if (a === '--voice') {
      voice = argv[++i] ?? voice;
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
      'usage: node speak.js <file.norm.md ...> | --dir FOLDER [--combos d/s,d/s] [--ssml] [--voice NAME] [--write DIR]'
    );
    process.exit(1);
  }
  return { files, combos, ssml, voice, write };
}

/* ----------------------------- SSML helpers ----------------------------- */

const escapeXml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** SRE SSML -> inner markup only (drop its <speak>/<prosody> envelope). */
function ssmlInner(s) {
  const pros = s.match(/<prosody[^>]*>([\s\S]*)<\/prosody>/);
  if (pros) return pros[1].trim();
  const speak = s.match(/<speak[^>]*>([\s\S]*)<\/speak>/);
  return (speak ? speak[1] : s).trim();
}

const AZURE_SSML = (voice, body) =>
  '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ko-KR">' +
  `<voice name="${voice}">${body}</voice></speak>`;

/**
 * Best-effort reading for LaTeX temml cannot parse (broken OCR output).
 * Keeps the human-readable content (\text bodies, numbers, operators) and
 * drops commands/braces — NEVER let a ParseError message reach the speech.
 */
/**
 * Post-SRE speech rewrites for SRE-ko misreads with a known better Korean form.
 * \Box (fill-in-the-blank □) is read "흰색 정사각형" (lit. "white square");
 * Korean math speech calls the blank "네모".
 */
function fixMisreads(speech) {
  return speech.replace(/흰색 정사각형/g, '네모');
}

const SALVAGE_KO = {
  pm: '플러스 마이너스', sqrt: '루트', times: '곱하기', div: '나누기',
  cdot: '곱하기', frac: '분수', pi: '파이', infty: '무한대',
  sin: '싸인', cos: '코싸인', tan: '탄젠트', leq: '작거나 같다', geq: '크거나 같다',
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
  const { files, combos, ssml, voice, write } = parseArgs(process.argv.slice(2));
  if (write) fs.mkdirSync(write, { recursive: true });
  const writeStitched = (file, content) => {
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
    return { file, text, parts: splitSpans(text) };
  });

  const mathml = new Map(); // latex -> {mathml} | {error}
  for (const doc of docs) {
    for (const part of doc.parts) {
      if (part.latex === undefined || mathml.has(part.latex)) continue;
      try {
        // throwOnError so broken LaTeX lands in the catch; belt-and-suspenders
        // <merror> check in case temml still renders an inline error message
        // (SRE would read it aloud: "백슬래시 ParseError 콜론 ...").
        const xml = temml.renderToString(part.latex, { xml: true, throwOnError: true });
        if (xml.includes('<merror')) throw new Error('temml emitted <merror>');
        mathml.set(part.latex, { mathml: xml });
      } catch (err) {
        mathml.set(part.latex, { error: String(err) });
      }
    }
  }

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

    console.log(hr);
    if (ssml) {
      console.log(`STITCHED SSML (${stitchKey}, Azure envelope, voice=${voice}):`);
      console.log(hr);
      const body = doc.parts
        .map((part) => {
          if (part.latex === undefined) return escapeXml(part.prose);
          const out = speech.get(part.latex).get(stitchKey);
          if (typeof out === 'string' && out.trim()) return ` ${ssmlInner(out)} `;
          const saved = salvage(part.latex);
          return saved ? ` ${escapeXml(saved)} ` : ` [지원되지 않는 수식: ${escapeXml(part.latex)}] `;
        })
        .join('')
        .replace(/ +/g, ' ')
        .trim();
      const doc_ssml = AZURE_SSML(voice, body);
      console.log(doc_ssml);
      writeStitched(doc.file, doc_ssml);
    } else {
      console.log(`STITCHED (${stitchKey}) — what a TTS voice would read:`);
      console.log(hr);
      const stitched = doc.parts
        .map((part) => {
          if (part.latex === undefined) return part.prose;
          const out = speech.get(part.latex).get(stitchKey);
          if (typeof out === 'string' && out.trim()) return ` ${out.trim()} `;
          const saved = salvage(part.latex);
          return saved ? ` ${saved} ` : ` [지원되지 않는 수식: ${part.latex}] `;
        })
        .join('')
        .replace(/ +/g, ' ')
        .trim();
      console.log(stitched);
      writeStitched(doc.file, stitched);
    }
  }
}

module.exports = { SPAN };

if (require.main === module) {
  main().catch((err) => {
    console.error('FATAL:', err);
    process.exit(1);
  });
}
