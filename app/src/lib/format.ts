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

/**
 * Splits the spoken text into phrases for the reading highlight, each with an
 * estimated start time. The backend returns no word timings, so a phrase's
 * start is proportional to the characters before it.
 */
export function phrases(text: string, duration: number): { text: string; start: number }[] {
  const words = text.split(/\s+/).filter(Boolean);
  const out: string[] = [];
  let cur: string[] = [];
  for (const w of words) {
    cur.push(w);
    if (/[,.?!。]$/.test(w) || cur.join(' ').length >= 14) {
      out.push(cur.join(' '));
      cur = [];
    }
  }
  if (cur.length) out.push(cur.join(' '));
  const total = out.reduce((n, p) => n + p.length, 0) || 1;
  let acc = 0;
  return out.map((p) => {
    const start = (acc / total) * duration;
    acc += p.length;
    return { text: p, start };
  });
}
