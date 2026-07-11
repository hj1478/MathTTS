/**
 * Capability probe: can speech-rule-engine (SRE) produce usable KOREAN speech for math?
 *
 * Pipeline under test:  LaTeX --temml--> MathML --SRE--> Korean speech string
 *
 * Run:  node index.js
 *
 * Verified against speech-rule-engine 5.0.0-rc.4:
 *   - setupEngine(options) returns a Promise -> must be awaited (async engine setup)
 *   - toSpeech(mathmlString) is then synchronous
 *   - available (locale, domain, style) combos are enumerated by the CLI `sre --opt`,
 *     which only lists LOADED locales, hence we invoke it with `-c ko`.
 */

'use strict';

const { execFileSync } = require('child_process');
const path = require('path');
const sre = require('speech-rule-engine');
const temml = require('temml');

const EXPRESSIONS = [
  '3(x-k) \\leq 2x+5',
  'p \\leq k < q',
  'p^2 + 9q^2',
  '\\frac{x+1}{2}',
  '\\frac{\\frac{a}{b}}{c+1}', // nested fraction — the stress case
  '\\sqrt{x^2 + 1}',
];

const HR = '='.repeat(78);
const hr = '-'.repeat(78);

/* ---------------------------------------------------------------- STEP 1 */

/**
 * Parse the `sre -c ko --opt` table and return, for locale "ko" and
 * modality "speech", a map domain -> [styles...].
 *
 * The table format is column-aligned:
 *   locale | modality | domain     | style
 *   ko     | speech   | clearspeak | AbsoluteValue_Auto, ...
 *          |          |            | Bar_Auto, ...            (continuation)
 *          |          | mathspeak  | brief, default, sbrief
 */
function probeKoreanCapabilities() {
  const sreBin = path.join(__dirname, 'node_modules', '.bin', 'sre');
  const out = execFileSync(process.execPath, [sreBin, '-c', 'ko', '--opt'], {
    encoding: 'utf8',
  });

  const domains = {}; // domain -> Set(styles)
  let curLocale = '';
  let curModality = '';
  let curDomain = '';

  for (const line of out.split('\n')) {
    if (!line.includes('|') || line.startsWith('=')) continue;
    const cols = line.split('|').map((c) => c.trim());
    if (cols.length < 4 || cols[0] === 'locale') continue;
    if (cols[0]) curLocale = cols[0];
    if (cols[1]) curModality = cols[1];
    if (cols[2]) curDomain = cols[2];
    if (curLocale !== 'ko' || curModality !== 'speech' || !curDomain) continue;
    const set = (domains[curDomain] ??= new Set());
    for (const s of cols[3].split(',').map((s) => s.trim()).filter(Boolean)) {
      set.add(s);
    }
  }
  return domains;
}

/* ---------------------------------------------------------------- STEP 2 */

function latexToMathML(latex) {
  // temml emits a self-contained <math> element; xml:true gives well-formed XML
  return temml.renderToString(latex, { xml: true });
}

/* ---------------------------------------------------------------- STEP 3 */

async function speak(mathml, locale, domain, style) {
  // setupEngine returns a promise; toSpeech is only reliable after it resolves
  await sre.setupEngine({ locale, domain, style, modality: 'speech', markup: 'none' });
  await sre.engineReady();
  return sre.toSpeech(mathml);
}

/* ------------------------------------------------------------------ main */

async function main() {
  console.log(HR);
  console.log('STEP 1 — CAPABILITY PROBE  (from `sre -c ko --opt`, SRE v' + sre.version + ')');
  console.log(HR);

  const koDomains = probeKoreanCapabilities();

  const hasClearspeak = 'clearspeak' in koDomains;
  const hasMathspeak = 'mathspeak' in koDomains;

  console.log();
  console.log(`  >>> Korean ClearSpeak: ${hasClearspeak ? 'AVAILABLE' : 'NOT AVAILABLE'}`);
  console.log(`  >>> Korean MathSpeak:  ${hasMathspeak ? 'AVAILABLE' : 'NOT AVAILABLE'}`);
  console.log();

  console.log('  All domains found for locale "ko" (modality: speech):');
  for (const [domain, styles] of Object.entries(koDomains)) {
    const list = [...styles];
    const shown = list.length > 8 ? list.slice(0, 8).join(', ') + `, ... (${list.length} total)` : list.join(', ');
    console.log(`    - ${domain}: ${shown}`);
  }
  console.log();
  console.log('  Note: clearspeak "styles" are combinatorial preference toggles');
  console.log('  (Fraction_Over, Roots_RootEnd, ...), not distinct named styles;');
  console.log('  the probe below runs clearspeak with style "default" (= all Auto).');

  // Build the combos we will actually generate speech for.
  const combos = [];
  if (hasMathspeak) {
    for (const style of ['default', 'brief', 'sbrief']) {
      if (koDomains.mathspeak.has(style)) combos.push({ domain: 'mathspeak', style });
    }
  }
  if (hasClearspeak) combos.push({ domain: 'clearspeak', style: 'default' });
  if (koDomains.default) {
    for (const style of koDomains.default) combos.push({ domain: 'default', style });
  }
  if (koDomains.emacspeak) combos.push({ domain: 'emacspeak', style: 'default' });

  /* -------- STEP 2: LaTeX -> MathML -------- */

  console.log();
  console.log(HR);
  console.log('STEP 2 — LaTeX -> MathML  (via temml, eyeball for fidelity)');
  console.log(HR);

  const converted = []; // {latex, mathml | error}
  for (const latex of EXPRESSIONS) {
    console.log();
    console.log(`LaTeX:  ${latex}`);
    try {
      const mathml = latexToMathML(latex);
      converted.push({ latex, mathml });
      console.log(`MathML: ${mathml}`);
    } catch (err) {
      converted.push({ latex, error: String(err) });
      console.log(`MathML: !! CONVERSION FAILED: ${err}`);
    }
  }

  /* -------- STEP 3: Korean speech per combo -------- */

  console.log();
  console.log(HR);
  console.log('STEP 3 — Korean speech per (domain, style)');
  console.log(HR);

  // Generate combo-outer / expression-inner (setupEngine is engine-global),
  // but collect results so we can PRINT grouped per expression.
  const results = new Map(); // latex -> [{domain, style, speech | error}]
  for (const { latex } of converted) results.set(latex, []);

  for (const { domain, style } of combos) {
    for (const item of converted) {
      const bucket = results.get(item.latex);
      if (item.error) {
        bucket.push({ domain, style, error: 'skipped (MathML conversion failed)' });
        continue;
      }
      try {
        const speech = await speak(item.mathml, 'ko', domain, style);
        // Sanity check: did the engine actually apply what we asked for?
        const setup = sre.engineSetup();
        const applied =
          setup.domain === domain && setup.style.toLowerCase() === style.toLowerCase()
            ? ''
            : `  [engine applied domain=${setup.domain} style=${setup.style}]`;
        bucket.push({ domain, style, speech, applied });
      } catch (err) {
        bucket.push({ domain, style, error: String(err) });
      }
    }
  }

  for (const [latex, bucket] of results) {
    console.log();
    console.log(hr);
    console.log(`LaTeX: ${latex}`);
    console.log(hr);
    for (const r of bucket) {
      const tag = `${r.domain}/${r.style}`.padEnd(22);
      if (r.error) {
        console.log(`  ${tag} !! ${r.error}`);
      } else {
        const flag = !r.speech || !r.speech.trim() ? '  << EMPTY OUTPUT' : '';
        console.log(`  ${tag} ${r.speech}${flag}${r.applied}`);
      }
    }
  }

  /* -------- summary -------- */

  console.log();
  console.log(HR);
  console.log('SUMMARY');
  console.log(HR);
  console.log(`  Korean ClearSpeak: ${hasClearspeak ? 'AVAILABLE' : 'NOT AVAILABLE'}`);
  console.log(`  Korean MathSpeak:  ${hasMathspeak ? 'AVAILABLE' : 'NOT AVAILABLE'}`);
  const bad = [];
  for (const [latex, bucket] of results) {
    if (bucket.some((r) => r.error || !r.speech || !r.speech.trim())) bad.push(latex);
  }
  console.log(
    bad.length
      ? `  Expressions with empty/failed output: ${bad.join('  |  ')}`
      : '  No empty or failed outputs.'
  );
}

main().catch((err) => {
  console.error('FATAL:', err);
  process.exit(1);
});
