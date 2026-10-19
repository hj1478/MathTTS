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
    };
  };
  audio?: { status: AudioStatus; message: string; url: string | null };
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

async function call(path: string, init?: RequestInit): Promise<any> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, init);
  } catch {
    throw new ApiError(0, 'network', OFFLINE_MESSAGE);
  }
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON error page (e.g. a proxy); fall through with a generic message.
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

/** Fire-and-forget: start a GPU worker while the user picks a photo. */
export function warmup(): void {
  fetch(API_URL + '/warmup', { method: 'POST' }).catch(() => {});
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
  const body = await call('/jobs', { method: 'POST', body: form });
  return body.id as string;
}

export function getJob(id: string): Promise<Job> {
  return call('/jobs/' + id);
}
