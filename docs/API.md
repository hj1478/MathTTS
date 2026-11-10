# MathTTS HTTP API

The backend in `backend/modal_app.py`, deployed on Modal. One image in; every
pipeline stage's output plus an MP3 out. Jobs are asynchronous: submit, poll,
then fetch the audio.

A typical client:

1. `POST /warmup` when the app opens (or the camera screen appears), so a GPU
   worker is starting while the user picks a photo.
2. `POST /jobs` with the photo.
3. Poll `GET /jobs/{id}`. Show `stages.ocr.text` as soon as it appears, then
   `stages.speech.text`; play the audio when `status` is `done`.

Base URL: the `web` endpoint that `modal deploy` prints. It may include a region
segment:

```
https://<workspace>--mathtts.modal.run
https://<workspace>--mathtts.<region>.modal.run     e.g. …--mathtts.us-east.modal.run
```

`modal serve` gives a temporary dev URL with `-dev` after the label, e.g.
`https://<workspace>--mathtts-dev.<region>.modal.run`.

There is no authentication. Abuse limits are listed under [Limits](#limits).

## Errors

Every error response, on every endpoint, has the same body:

```json
{ "error": { "code": "file_too_large", "message": "이미지는 5MB 이하만 올릴 수 있습니다." } }
```

`code` is stable and machine-readable. `message` is Korean text you can show to
the user as is.

Besides the per-endpoint errors below, any endpoint can return:

| Status | `code` | When |
|---|---|---|
| 404 | `not_found` | Unknown path |
| 405 | `method_not_allowed` | Wrong method for the path (e.g. `GET /jobs`) |
| 500 | `internal_error` | An unexpected server error. Retrying later usually works |

---

## `POST /warmup` — start a worker ahead of the upload

No body. Starts a GPU worker container in the background (it loads the OCR
model; no OCR runs) and returns at once, without waiting for it.

```sh
curl -X POST https://<workspace>--mathtts.<region>.modal.run/warmup
```

**`202 Accepted`**

```json
{ "status": "warming" }
```

Call it when the app opens. It is fire-and-forget: there is nothing to poll,
and a job submitted while the worker is still loading simply waits for it,
rather than starting a second cold worker.

- A cold start (no worker running) takes about 30 s before a job can start
  OCR. Calling `/warmup` early moves that time off the user's wait: with
  `/warmup` sent 20 s before the upload, a cold job finished in 35 s instead
  of 50 s (FINDINGS.md, 2026-10-17). About 30 s of lead hides it fully.
- If a worker is already idle, the call does nothing except restart its idle
  timer.
- A worker stays up for 90 s after its last call (`/warmup` or a job), then
  scales to zero. If the user is likely to take longer than that before
  uploading, call `/warmup` again, e.g. when they open the camera or pick a
  photo.
- It has its own per-IP budget, separate from jobs: warming never uses up one
  of the 10 jobs/hour.

| Status | `code` | When |
|---|---|---|
| 429 | `rate_limited` | Over 30 warmups this clock hour from this IP. `Retry-After` gives the seconds until the next hour starts. Safe to ignore: the job still runs, only colder |

## `POST /jobs` — submit one image

`multipart/form-data` with a single file field named **`image`**.

```sh
curl -F "image=@kr question 1.png" https://<workspace>--mathtts.<region>.modal.run/jobs
```

The upload is checked in this order, all before any GPU work starts:
size → type (from the file bytes, not the declared Content-Type) → decodable →
per-IP rate limit. A rejected upload does not use up a rate-limit slot, except
a `429`.

**`202 Accepted`**

```json
{ "id": "3f9c0a1b2c3d4e5f60718293", "status": "queued", "status_url": "/jobs/3f9c0a1b2c3d4e5f60718293" }
```

| Status | `code` | When |
|---|---|---|
| 400 | `bad_request` | Not multipart, or no `image` file field |
| 400 | `empty_file` | The file is 0 bytes |
| 411 | `length_required` | No `Content-Length` (chunked upload); the size must be known up front |
| 413 | `file_too_large` | Larger than 5 MB (5 × 1024 × 1024 bytes) |
| 415 | `unsupported_type` | Not PNG, JPEG, WebP, BMP or TIFF |
| 415 | `heic_not_supported` | HEIC/HEIF/AVIF (iPhone default); convert to JPEG or PNG |
| 422 | `invalid_image` | The bytes look like an image but don't decode, or it has more than 40 megapixels |
| 429 | `rate_limited` | Over 10 jobs this clock hour from this IP. The `Retry-After` header gives the seconds until the next hour starts |
| 503 | `service_unavailable` | The GPU job could not be started (a Modal error). No rate-limit slot is used; retry in a little while |

## `GET /jobs/{id}` — status and results

Poll every 0.5 s, counted from the start of the previous poll (a poll takes ~0.3 s). A job record lives for 24 hours after creation.

Each stage's output is in `stages` **as soon as that stage finishes**, while
later stages are still running. The OCR text arrives first, then the spoken
text, and the audio last. Show text as it arrives; don't wait for `done`.
`stage_status` gives the state of each of the four stages.

**`200 OK`**, while the job is in progress. Here OCR and normalization are
finished and stage 3 is running:

```json
{
  "id": "3f9c0a1b2c3d4e5f60718293",
  "status": "running",
  "stage": "speech",
  "stage_status": { "ocr": "done", "normalize": "done", "speech": "running", "tts": "pending" },
  "created_at": 1792112400,
  "expires_at": 1792198800,
  "stages": {
    "ocr":        { "text": "…" },
    "normalized": { "text": "…" },
    "math_spans": [ … ]
  }
}
```

`stages` is absent until OCR has finished. Each entry, once present, is final
and does not change. While the job runs, `stages` holds only the finished
entries:

| Stage finished | Entries added to `stages` |
|---|---|
| `ocr` | `ocr` |
| `normalize` | `normalized`, `math_spans` |
| `speech` | `speech` (the spoken text, which can be shown while the audio is made) |
| `tts` | none; `audio` appears with `status: "done"` |

`stage_status` always has all four keys, in pipeline order (`ocr`, `normalize`,
`speech`, `tts`), each one of:

| State | Meaning |
|---|---|
| `pending` | Not started yet |
| `running` | In progress now |
| `done` | Finished; its output is in `stages` (or, for `tts`, the audio is ready) |
| `skipped` | Will not run. For `tts`: the speech has a placeholder (`strict_ok` is `false`), which is known as soon as `speech` is done; or the job failed at an earlier stage |
| `failed` | The job failed in this stage (`status: "failed"`), or for `tts`, `audio.status` is `quota_reached` or `failed` |

| `status` | Meaning |
|---|---|
| `queued` | Waiting for a worker. At most 2 GPU workers run at once; extra jobs wait in line. A cold start (no idle worker) adds model-load time. |
| `running` | `stage` is one of `ocr`, `normalize`, `speech`, `tts`, the one now running |
| `done` | Final. Includes all of `stages`, plus `audio` and `timings_s` (below) |
| `failed` | Final. Includes `error` (below), and `stages` for every stage that finished before the failure |

**`200 OK`**, `done`:

```json
{
  "id": "3f9c0a1b2c3d4e5f60718293",
  "status": "done",
  "stage": null,
  "stage_status": { "ocr": "done", "normalize": "done", "speech": "done", "tts": "done" },
  "created_at": 1792112400,
  "expires_at": 1792198800,
  "stages": {
    "ocr":        { "text": "<OCR markdown, LaTeX in $…$ / $$…$$>" },
    "normalized": { "text": "<the same text after normalize.normalize_math>" },
    "math_spans": [
      { "source": "$x^2+1$", "latex": "x^2+1", "display": false }
    ],
    "speech": {
      "text": "<the Korean text that is read aloud>",
      "ssml": "<speak …>…</speak>",
      "strict_ok": true,
      "summary": ["SUMMARY: 3 span(s), ok: 3", "(ssml) SUMMARY: 3 span(s), ok: 3"],
      "korean_present": true
    }
  },
  "audio": {
    "status": "ready",
    "message": "음성이 준비되었습니다.",
    "url": "https://<workspace>--mathtts.<region>.modal.run/audio/3f9c0a1b2c3d4e5f60718293"
  },
  "timings_s": { "ocr": 4.1, "speech": 1.3, "tts": 2.2 }
}
```

The stages, in pipeline order:

| Field | Pipeline stage |
|---|---|
| `stages.ocr.text` | Stage 1, PaddleOCR-VL (`ocr_vl.run_image`): markdown with LaTeX |
| `stages.normalized.text` | Stage 2, `normalize.normalize_math` |
| `stages.math_spans` | The math spans extracted from the normalized text, in reading order (`ocr_vl.analyze`). `latex` is `source` without its `$` delimiters |
| `stages.speech.text` | Stage 3, `sre-probe/speak.js` (Temml → speech-rule-engine, Korean): the final spoken text |
| `stages.speech.ssml` | Stage 3 `--ssml` output, which is what stage 4 sends to Azure. `null` if it was not produced |
| `stages.speech.strict_ok` | `false` when a formula stitched as salvage or a placeholder (speak.js `--strict`). The text is still returned, but no audio is made (`audio.status` = `skipped`) |
| `audio` | Stage 4, Azure TTS (`ko-KR-SunHiNeural`) |

`audio.status`. A finished job is `done` whatever its audio status: the text
stages are the result.

| `audio.status` | `url` | Meaning |
|---|---|---|
| `ready` | set | The MP3 is at `url` |
| `quota_reached` | `null` | Azure answered 429 / quota exhausted (F0 free tier). The message says the monthly limit was reached |
| `skipped` | `null` | `strict_ok` is `false`, so Azure was not asked to read a placeholder aloud |
| `failed` | `null` | Azure failed for another reason, after one retry |

### Two readings

`stages.speech` is the casual reading (speak.js `--casual`: "3 이상", "x 마이너스
1 분의 x 플러스 1"). When the formal reading (math spelled out, without
`--casual`) could be made too, its text is added so a client can let the
listener switch:

```json
"stages": { "speech": { "text": "…", "ssml": "…", "strict_ok": true, "summary": [],
    "formal": { "text": "…", "ssml": "…", "strict_ok": true, "summary": [] } } }
```

- `formal` is an extra: it is absent when speak.js could not make it, and
  that never fails the job. On a page with several problems each problem has
  its own `speech.formal`; the page's is their texts joined.
- The job does not send the formal reading to Azure. Its MP3 is made when a
  listener asks for it:

  `POST /jobs/{id}/formal-audio` (one problem), or
  `POST /jobs/{id}/formal-audio?problem=N` (problem N, 1-based, of a page)

  answers `{ "status", "message", "url" }` like an `audio` entry. `ready`:
  the MP3 is at `url` (`GET /audio/{id}?style=formal`,
  `GET /audio/{id}/{N}?style=formal`), kept as long as the job. Asking again
  returns the stored MP3 without another Azure call. From then on
  `GET /jobs/{id}` shows it as `audio.formal` (or `audio.problems[i].formal`).
  `skipped`: the formal text has a placeholder; nothing is sent. `quota_reached`
  / `failed`: nothing was stored, and it can be asked again.
- Errors: `404` (unknown job, no formal reading, or the page itself on a page
  of problems), `409 not_done`, `429` (30 requests an hour per IP, apart from
  the job budget).

### Pages with several problems

When the photo holds two or more numbered problems ("1.", "2)", "[3]",
"문제 4"), each one is read separately (`backend/problems.py`), so a client can
highlight and play them one at a time. Such a job also has
`stages.problems` (added just before `stages.speech`) and `audio.problems`:

```json
"stages": { "problems": [
  { "label": "27",
    "boxes": [[0.0672, 0.0446, 0.4698, 0.1323]],
    "normalized": { "text": "27. 다음 조건을 …" },
    "speech": { "text": "27. 다음 조건을 …", "ssml": "<speak …>", "strict_ok": true, "summary": [] } },
  …
] },
"audio": { "status": "ready", "message": "…", "url": "…/audio/<id>",
  "problems": [ { "status": "ready", "message": "…", "url": "…/audio/<id>/1" }, … ] }
```

- `boxes` are where the problem is on the uploaded image, as fractions of its
  width and height: `[x0, y0, x1, y1]`, one rectangle per column the problem
  spans (a figure or table under it is included).
- Each problem has its own `--strict` guard and audio status: one formula
  speak.js can't read skips that problem's audio only (`skipped`). A problem
  speak.js crashed on has empty speech and audio `failed`; if it crashed on
  every problem, the job fails with `speech_stage_failed`, as for one problem.
- When no problem can be read aloud, stage 4 does not run: `stage_status.tts`
  is `skipped` and `timings_s.tts` is absent.
- Every problem is labelled the way the first one is ("1." on a "1." page),
  so a "3)" sub-item inside a problem is not a new problem.
- `audio.problems[i]` belongs to `stages.problems[i]`; its MP3 is
  `GET /audio/{id}/{i+1}`.
- The page's own `stages.speech.text` is the problems' texts joined, and its
  `ssml` is `null`. The page `audio` is every problem's MP3 back to back when
  all are `ready`; otherwise its status is the first of `quota_reached`,
  `failed`, `skipped` found among the problems, and `url` is `null`.
- A photo with zero or one numbered problem has neither field and works as
  described above.

`timings_s` holds server-side seconds per stage. `tts` is absent when stage 4
did not run.

**`200 OK`**, `failed`:

```json
{
  "id": "…", "status": "failed", "stage": null,
  "stage_status": { "ocr": "failed", "normalize": "skipped", "speech": "skipped", "tts": "skipped" },
  "created_at": 1792112400, "expires_at": 1792198800,
  "error": { "code": "no_text_found", "message": "이미지에서 문제를 찾지 못했습니다. …" }
}
```

A job that fails after OCR (e.g. `speech_stage_failed`) still has
`stages.ocr`, `stages.normalized` and `stages.math_spans`.

| `error.code` | Meaning |
|---|---|
| `ocr_failed` | The OCR stage raised an error |
| `no_text_found` | The OCR returned no text |
| `speech_stage_failed` | speak.js crashed or wrote no output |
| `timeout` | The OCR call did not finish within 300 s and was killed, or the job hit the 420 s limit. Retrying usually works |
| `internal_error` | Any other worker error |
| `worker_lost` | The worker died without reporting (out of memory, a lost container). Reported once the job has gone 10 s without progress and Modal confirms the call has ended; also when a job never reached a worker (queued for 60 s with no call recorded), or stayed `running` for 480 s with no progress |

**Errors:** `404 not_found` for an unknown id, or a job older than 24 hours.

## `GET /audio/{id}` — the audio (MP3)

**`200 OK`**, `Content-Type: audio/mpeg`, with
`Content-Disposition: attachment; filename="mathtts-<id>.mp3"`. MP3, 24 kHz
mono, 48 kbit/s (about 6 KB per second of speech).

**Errors:** `404 not_found` if the job has no audio (`audio.status` is not
`ready`), the id is unknown, or the file is older than 24 hours.

## `GET /audio/{id}/{n}` — one problem's audio (MP3)

Problem `n` (1-based) of a page with several problems; the URL is
`audio.problems[n-1].url`. Same format and errors as `GET /audio/{id}`.

---

## Limits

| Limit | Value | Where it is set (`backend/`) |
|---|---|---|
| Upload size | 5 MB | `limits.MAX_UPLOAD_BYTES` |
| Image types | PNG, JPEG, WebP, BMP, TIFF | `limits.sniff_image` |
| Jobs per client IP | 10 per clock hour, shared across web containers (`modal.Dict`). An IPv6 client is counted by its /64 prefix | `modal_app.RATE_LIMIT_PER_HOUR`, `limits.client_key` |
| Warmups per client IP | 30 per clock hour, separate from the job budget | `modal_app.WARMUP_LIMIT_PER_HOUR` |
| Concurrent GPU workers | 2 (T4); more jobs queue | `modal_app.MAX_WORKERS` |
| Worker idle timeout | 90 s after the last job or warmup, then it scales to zero | `modal_app.SCALEDOWN_S` |
| OCR call | 300 s, then the OCR process is killed (`timeout`) | `modal_app.OCR_CUTOFF_S` |
| Job timeout | 420 s (Modal function timeout, a backstop) | `modal_app.JOB_TIMEOUT_S` |
| Retention | 24 h for uploads, stage files, audio and job records (cleanup runs hourly) | `modal_app.RETENTION_S` |

**CORS:** only browser origins listed in `MATHTTS_CORS_ORIGINS` at deploy
time, plus localhost dev ports (3000, 5173 and 8081 on `localhost`; 3000 and
5173 on `127.0.0.1`). Methods are `GET` and `POST`, and `Retry-After` is
exposed to scripts. Non-browser clients (curl, native apps) are not affected
by CORS.
