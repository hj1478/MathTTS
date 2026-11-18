// Korean dates and times as the designs write them ("오늘 오후 3:24", "10월 14일").

function clock(d: Date): string {
  const h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${h < 12 ? '오전' : '오후'} ${h % 12 || 12}:${m}`;
}

function dayDiff(d: Date, now = new Date()): number {
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const b = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((b - a) / 86400000);
}

export function isToday(ms: number): boolean {
  return dayDiff(new Date(ms)) === 0;
}

export function when(ms: number): string {
  const d = new Date(ms);
  const diff = dayDiff(d);
  if (diff === 0) return '오늘 ' + clock(d);
  if (diff === 1) return '어제 ' + clock(d);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

/** Screen-reader form: "오늘 오후 3시 24분". */
export function whenSpoken(ms: number): string {
  return when(ms).replace(/(\d+):(\d+)/, (_, h, m) => `${h}시 ${Number(m)}분`);
}

/** Player time, "0:05". */
export function mmss(s: number): string {
  const v = Math.max(0, Math.floor(s));
  return Math.floor(v / 60) + ':' + String(v % 60).padStart(2, '0');
}

/** Elapsed time on the processing screen, "1분 42초". */
export function elapsed(s: number): string {
  const v = Math.max(0, Math.floor(s));
  return `${Math.floor(v / 60)}분 ${String(v % 60).padStart(2, '0')}초`;
}

export function megabytes(bytes: number): string {
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

/** OCR markdown → one plain line for history rows: drop $ delimiters and LaTeX commands. */
export function plainPreview(md: string): string {
  return md
    .replace(/\$\$?([^$]*)\$\$?/g, (_, m: string) =>
      m
        .replace(/\\frac\{([^}]*)\}\{([^}]*)\}/g, '$1/$2')
        .replace(/\\(left|right|displaystyle|,|;|!)/g, '')
        .replace(/\\times/g, '×')
        .replace(/\\cdot/g, '·')
        .replace(/\\le(q)?/g, '≤')
        .replace(/\\ge(q)?/g, '≥')
        .replace(/\\pm/g, '±')
        .replace(/\\angle/g, '∠')
        .replace(/\^\{?\\circ\}?/g, '°')
        .replace(/\^\{?2\}?/g, '²')
        .replace(/\^\{?3\}?/g, '³')
        .replace(/\\sqrt\{([^}]*)\}/g, '√$1')
        .replace(/\\[a-zA-Z]+/g, '')
        .replace(/[{}]/g, '')
        .replace(/-/g, '−'),
    )
    .replace(/[#*_>`]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export interface Segment {
  md: string; // a piece of the problem as OCR markdown (prose and $…$ formulas)
  start: number; // seconds into the audio, estimated
}

const MATH = /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\$[^$\n]+?\$|\\\([\s\S]+?\\\)/g;
const CHOICE = /[①-⑳]/g;

/**
 * Splits the problem (not the spoken sentence) into phrases for the reading
 * highlight, each with an estimated start time.
 *
 * The backend returns no word timings, so a phrase's start is proportional to
 * the spoken characters before it. A word of prose is spoken as written; how
 * long a formula's reading is comes from the spoken sentence, where it is the
 * words between the prose on either side of it.
 */
export function readingSegments(problem: string, spoken: string, duration: number): Segment[] {
  // words and formulas, each keeping the white space after it
  const toks: { md: string; math: boolean; word: string }[] = [];
  const prose = (t: string) => {
    for (const m of t.matchAll(/\S+\s*/g)) toks.push({ md: m[0], math: false, word: m[0].trim().replace(/^#+$|\*\*/g, '') });
  };
  let last = 0;
  for (const m of problem.matchAll(MATH)) {
    prose(problem.slice(last, m.index));
    const gap = /^\s*/.exec(problem.slice(m.index + m[0].length))![0];
    const prev = toks[toks.length - 1];
    // two formulas in a row are one stretch of speech with nothing to tell them apart
    if (prev?.math && last === m.index) prev.md += m[0] + gap;
    else toks.push({ md: m[0] + gap, math: true, word: '' });
    last = m.index + m[0].length + gap.length;
  }
  prose(problem.slice(last));

  const said = spoken.replace(/^#+\s*/gm, '').replace(/\*\*/g, '').split(/\s+/).filter(Boolean);
  const chars = (from: number, to: number) => said.slice(from, to).reduce((n, w) => n + w.length + 1, 0);
  let at = 0;
  const weight = toks.map((t, k) => {
    if (!t.math) {
      // a choice number is one character on screen but about ten in the audio:
      // it is said "1번", with a pause on each side (sre-probe/speak.js speakMarks)
      const w = t.word.length + 1 + 9 * (t.word.match(CHOICE)?.length ?? 0);
      // the problem number is said "3번" and then a pause (speakProblemLabels)
      const label = k === 0 && /^\d{1,3}\.$/.test(t.word) ? 6 : 0;
      const j = said.indexOf(t.word, at);
      if (j >= 0 && j <= at + 3) at = j + 1;
      return w + label;
    }
    // the formula's reading runs up to the next two words of prose
    const n1 = toks[k + 1];
    const n2 = toks[k + 2];
    let end = n1 ? -1 : said.length;
    for (let j = at; n1 && j < said.length; j++) {
      if (said[j] === n1.word && (!n2 || n2.math || said[j + 1] === n2.word)) {
        end = j;
        break;
      }
    }
    if (end < at) return 2 * t.md.replace(/\\[a-zA-Z]+|[${}\s]/g, '').length + 2; // not found: a guess
    const w = chars(at, end);
    at = end;
    return Math.max(w, 1);
  });

  // phrases: up to a comma or full stop, or about 14 spoken characters
  const out: { md: string; w: number }[] = [];
  let cur = { md: '', w: 0 };
  const close = () => {
    const prev = out[out.length - 1];
    // a word or two left over after a long formula ("이다.", "때,") stays with it
    if (prev && cur.w < 5 && !/\n\s*$/.test(prev.md) && !/[$\u2460-\u2473]/.test(cur.md)) {
      prev.md += cur.md;
      prev.w += cur.w;
    } else if (cur.md) out.push(cur);
    cur = { md: '', w: 0 };
  };
  toks.forEach((t, k) => {
    if (!t.math && /^[\u2460-\u2473]/.test(t.word)) close(); // each answer choice is its own phrase
    cur.md += t.md;
    cur.w += weight[k]!;
    if ((!t.math && /[,.?!。]$/.test(t.word)) || cur.w >= 14 || /\n\s*$/.test(t.md)) close();
  });
  close();
  const total = out.reduce((n, p) => n + p.w, 0) || 1;
  let acc = 0;
  return out.map((p) => {
    const start = (acc / total) * duration;
    acc += p.w;
    return { md: p.md, start };
  });
}
