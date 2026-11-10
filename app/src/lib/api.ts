// Client for the backend in backend/modal_app.py. The contract is docs/API.md.
import { Platform } from 'react-native';

export const API_URL = (
  process.env.EXPO_PUBLIC_API_URL ?? 'https://joshuayoomin--mathtts.modal.run'
).replace(/\/$/, '');

export type StageName = 'ocr' | 'normalize' | 'speech' | 'tts';
export type StageState = 'pending' | 'running' | 'done' | 'skipped' | 'failed';
export type AudioStatus = 'ready' | 'quota_reached' | 'skipped' | 'failed';

export interface MathSpan {
  source: string;
  latex: string;
  display: boolean;
}

/** The formal reading (math spelled out), when the backend made one (docs/API.md, Two readings). */
export interface FormalSpeech {
  text: string;
  ssml: string | null;
  strict_ok: boolean;
  summary: string[];
}

/** One numbered problem of a page with several (docs/API.md, Problems). */
export interface JobProblem {
  label: string; // the printed number, e.g. "3"
  boxes: [number, number, number, number][]; // x0, y0, x1, y1 as fractions of the photo
  normalized: { text: string };
  speech: { text: string; ssml: string | null; strict_ok: boolean; summary: string[]; formal?: FormalSpeech };
}

export interface AudioEntry {
  status: AudioStatus;
  message: string;
  url: string | null;
}

export interface ProblemAudio extends AudioEntry {
  formal?: AudioEntry;
}

export interface Job {
  id: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  stage: StageName | null;
  stage_status: Record<StageName, StageState>;
  created_at: number;
  expires_at: number;
  stages?: {
    ocr?: { text: string };
    normalized?: { text: string };
    math_spans?: MathSpan[];
    speech?: {
      text: string;
      ssml: string | null;
      strict_ok: boolean;
      summary: string[];
      korean_present: boolean;
      formal?: FormalSpeech;
    };
    problems?: JobProblem[]; // only for a page with two or more numbered problems
  };
  audio?: ProblemAudio & { problems?: ProblemAudio[] };
  timings_s?: Partial<Record<StageName, number>>;
  error?: { code: string; message: string };
}

/** An error the backend answered with, or a network failure (`status` 0). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

const OFFLINE_MESSAGE = '연결이 끊겼어요. 사진은 그대로 있어요.';

// Without a deadline a request can hang for good (Android's HTTP client has no
// read timeout), and the poll loop waits on it forever.
const GET_TIMEOUT_MS = 10_000;
const UPLOAD_TIMEOUT_MS = 60_000;
const FORMAL_AUDIO_TIMEOUT_MS = 60_000; // a container start, then one Azure call

async function call(path: string, init?: RequestInit, ms = GET_TIMEOUT_MS): Promise<any> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms); // covers reading the body too
  let res: Response;
  let body: any = null;
  try {
    try {
      res = await fetch(API_URL + path, { ...init, signal: ctl.signal });
    } catch {
      throw new ApiError(0, 'network', OFFLINE_MESSAGE);
    }
    try {
      body = await res.json();
    } catch {
      if (ctl.signal.aborted) throw new ApiError(0, 'network', OFFLINE_MESSAGE);
      // Non-JSON error page (e.g. a proxy); fall through with a generic message.
    }
  } finally {
    clearTimeout(t);
  }
  if (!res.ok) {
    const retry = Number(res.headers.get('retry-after'));
    throw new ApiError(
      res.status,
      body?.error?.code ?? 'http_' + res.status,
      body?.error?.message ?? '서버에서 오류가 났어요. 잠시 후 다시 시도해 주세요.',
      Number.isFinite(retry) && retry > 0 ? retry : undefined,
    );
  }
  return body;
}

// The worker stops 90 s after its last request, so one warmup a minute keeps it
// up; more only spends the per-IP budget (30 an hour, shared by everyone behind
// one school network address). Remembered in localStorage on web, so reloads
// and other tabs count too.
const WARM_GAP_MS = 60_000;
const WARM_KEY = 'mathtts.warmAt';
let warmAt = 0;

function lastWarm(): number {
  if (Platform.OS === 'web') {
    try {
      return Math.max(warmAt, Number(window.localStorage.getItem(WARM_KEY)) || 0);
    } catch {
      // storage blocked: this page's memory only
    }
  }
  return warmAt;
}

/** The worker is known to be up or starting (a job was sent or answered). */
function markWarm(): void {
  warmAt = Date.now();
  if (Platform.OS === 'web') {
    try {
      window.localStorage.setItem(WARM_KEY, String(warmAt));
    } catch {
      // storage blocked
    }
  }
}

/** Fire-and-forget: start a GPU worker while the user picks a photo. Skipped
 * if one was started (or a job ran) in the last minute, unless `force`. */
export function warmup(force = false): void {
  if (!force && Date.now() - lastWarm() < WARM_GAP_MS) return;
  markWarm();
  call('/warmup', { method: 'POST' }).catch(() => {});
}

export interface UploadImage {
  uri: string;
  mimeType: string;
  name: string;
}

export async function submitJob(img: UploadImage): Promise<string> {
  const form = new FormData();
  if (Platform.OS === 'web') {
    const blob = await (await fetch(img.uri)).blob();
    form.append('image', blob, img.name);
  } else {
    // React Native's FormData takes a file descriptor object.
    form.append('image', { uri: img.uri, name: img.name, type: img.mimeType } as any);
  }
  const body = await call('/jobs', { method: 'POST', body: form }, UPLOAD_TIMEOUT_MS);
  markWarm(); // the job starts (or keeps) a worker
  return body.id as string;
}

/**
 * Ask for the formal reading's MP3 (of problem `problem`, 1-based, on a page of
 * several). The server sends it to Azure only now, and only the first time.
 * A `status` other than `ready` means no MP3 was made this time.
 */
export async function requestFormalAudio(id: string, problem?: number): Promise<AudioEntry> {
  const query = problem ? '?problem=' + problem : '';
  return call(`/jobs/${id}/formal-audio${query}`, { method: 'POST' }, FORMAL_AUDIO_TIMEOUT_MS);
}

export async function getJob(id: string): Promise<Job> {
  const job: Job = await call('/jobs/' + id);
  if (job.status !== 'failed') markWarm(); // a worker is starting, busy, or just finished
  return job;
}
