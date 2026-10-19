// Client for the MathTTS backend (../docs/API.md).

export const API_URL = (
  process.env.EXPO_PUBLIC_API_URL ?? 'https://joshuayoomin--mathtts.us-east.modal.run'
).replace(/\/+$/, '');

export type StageName = 'ocr' | 'normalize' | 'speech' | 'tts';
export type StageState = 'pending' | 'running' | 'done' | 'skipped' | 'failed';
export type JobStatus = 'queued' | 'running' | 'done' | 'failed';
export type AudioStatus = 'ready' | 'quota_reached' | 'skipped' | 'failed' | 'not_requested';

export type Job = {
  id: string;
  status: JobStatus;
  stage: StageName | null;
  stage_status: Record<StageName, StageState>;
  created_at: number;
  expires_at: number;
  stages?: {
    ocr?: { text: string };
    normalized?: { text: string };
    speech?: { text: string; strict_ok: boolean };
  };
  audio?: { status: AudioStatus; message: string; url: string | null };
  error?: { code: string; message: string };
};

/** An error the backend described (docs/API.md "Errors"), or a network failure. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status = 0,
    readonly retryAfterS: number | null = null,
  ) {
    super(message);
  }
}

const NETWORK_MESSAGE = '서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.';

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError('network', NETWORK_MESSAGE);
  }
  if (res.ok) return res;
  let code = 'http_error';
  let message = `서버 오류가 발생했습니다 (${res.status}).`;
  try {
    const body = await res.json();
    code = body.error?.code ?? code;
    message = body.error?.message ?? message;
  } catch {
    // not the JSON error body (e.g. a proxy error page)
  }
  const retry = Number(res.headers.get('Retry-After'));
  throw new ApiError(code, message, res.status, Number.isFinite(retry) && retry > 0 ? retry : null);
}

/** Start a GPU worker ahead of the upload. Fire-and-forget: failures are ignored. */
export function warmup(): void {
  request('/warmup', { method: 'POST' }).catch(() => {});
}

/** The upload as multipart form data: a Blob on web, a file URI on native. */
export type UploadImage = { uri: string; name: string; type: string; blob?: Blob };

export async function createJob(image: UploadImage): Promise<string> {
  const form = new FormData();
  if (image.blob) {
    form.append('image', image.blob, image.name);
  } else {
    // React Native's FormData takes a file descriptor object
    form.append('image', { uri: image.uri, name: image.name, type: image.type } as unknown as Blob);
  }
  const res = await request('/jobs', { method: 'POST', body: form });
  return (await res.json()).id;
}

export async function getJob(id: string, signal?: AbortSignal): Promise<Job> {
  const res = await request(`/jobs/${encodeURIComponent(id)}`, { signal });
  return res.json();
}
