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

// same span grammar as normalize.py: $$block$$ | $inline$. Inline may not
// contain Hangul/'$'/newline so a stray '$' in prose can't swallow text.
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

/** Split text into alternating prose / math-span parts, keeping order. */
function splitSpans(text) {
  const parts = []; // {prose} | {latex}
  let last = 0;
  for (const m of text.matchAll(SPAN)) {
    if (m.index > last) parts.push({ prose: text.slice(last, m.index) });
    const raw = m[0];
    const latex = raw.startsWith('$$') ? raw.slice(2, -2) : raw.slice(1, -1);
    parts.push({ latex: latex.trim() });
    last = m.index + raw.length;
  }
  if (last < text.length) parts.push({ prose: text.slice(last) });
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
        mathml.set(part.latex, { mathml: temml.renderToString(part.latex, { xml: true }) });
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
        speech.get(latex).set(key, sre.toSpeech(conv.mathml));
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
          return typeof out === 'string' && out.trim()
            ? ` ${ssmlInner(out)} `
            : ` [지원되지 않는 수식: ${escapeXml(part.latex)}] `;
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
          return typeof out === 'string' && out.trim() ? ` ${out.trim()} ` : ` [지원되지 않는 수식: ${part.latex}] `;
        })
        .join('')
        .replace(/ +/g, ' ')
        .trim();
      console.log(stitched);
      writeStitched(doc.file, stitched);
    }
  }
}

main().catch((err) => {
  console.error('FATAL:', err);
  process.exit(1);
});
