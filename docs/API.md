# MathTTS HTTP API

The backend in `backend/modal_app.py`, deployed on Modal. One image in; every
pipeline stage's output plus a wav out. Jobs are asynchronous: submit, poll,
then fetch the audio.

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

---

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

## `GET /jobs/{id}` — status and results

Poll every 1–2 s. A job record lives for 24 hours after creation.

**`200 OK`**, while the job is in progress:

```json
{
  "id": "3f9c0a1b2c3d4e5f60718293",
  "status": "running",
  "stage": "speech",
  "created_at": 1792112400,
  "expires_at": 1792198800
}
```

| `status` | Meaning |
|---|---|
| `queued` | Waiting for a worker. At most 2 GPU workers run at once; extra jobs wait in line. A cold start (no idle worker) adds model-load time. |
| `running` | `stage` is one of `ocr`, `normalize`, `speech`, `tts` |
| `done` | Final. Includes `stages`, `audio` and `timings_s` (below) |
| `failed` | Final. Includes `error` (below) |

**`200 OK`**, `done`:

```json
{
  "id": "3f9c0a1b2c3d4e5f60718293",
  "status": "done",
  "stage": null,
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
| `ready` | set | The wav is at `url` |
| `quota_reached` | `null` | Azure answered 429 / quota exhausted (F0 free tier). The message says the monthly limit was reached |
| `skipped` | `null` | `strict_ok` is `false`, so Azure was not asked to read a placeholder aloud |
| `failed` | `null` | Azure failed for another reason, after one retry |

`timings_s` holds server-side seconds per stage. `tts` is absent when stage 4
did not run.

**`200 OK`**, `failed`:

```json
{
  "id": "…", "status": "failed", "stage": null, "created_at": 1792112400, "expires_at": 1792198800,
  "error": { "code": "no_text_found", "message": "이미지에서 문제를 찾지 못했습니다. …" }
}
```

| `error.code` | Meaning |
|---|---|
| `ocr_failed` | The OCR stage raised an error |
| `no_text_found` | The OCR returned no text |
| `speech_stage_failed` | speak.js crashed or wrote no output |
| `timeout` | The OCR call did not finish within 300 s and was killed, or the job hit the 420 s limit. Retrying usually works |
| `internal_error` | Any other worker error |
| `worker_lost` | The worker died without reporting (out of memory, a lost container) |

**Errors:** `404 not_found` for an unknown id, or a job older than 24 hours.

## `GET /audio/{id}` — the wav

**`200 OK`**, `Content-Type: audio/wav`, with
`Content-Disposition: attachment; filename="mathtts-<id>.wav"`.

**Errors:** `404 not_found` if the job has no audio (`audio.status` is not
`ready`), the id is unknown, or the file is older than 24 hours.

---

## Limits

| Limit | Value | Where it is set (`backend/`) |
|---|---|---|
| Upload size | 5 MB | `limits.MAX_UPLOAD_BYTES` |
| Image types | PNG, JPEG, WebP, BMP, TIFF | `limits.sniff_image` |
| Jobs per client IP | 10 per clock hour, shared across web containers (`modal.Dict`) | `modal_app.RATE_LIMIT_PER_HOUR` |
| Concurrent GPU workers | 2 (T4); more jobs queue | `modal_app.MAX_WORKERS` |
| Worker idle timeout | 90 s, then it scales to zero | `modal_app.SCALEDOWN_S` |
| OCR call | 300 s, then the OCR process is killed (`timeout`) | `modal_app.OCR_CUTOFF_S` |
| Job timeout | 420 s (Modal function timeout, a backstop) | `modal_app.JOB_TIMEOUT_S` |
| Retention | 24 h for uploads, stage files, audio and job records (cleanup runs hourly) | `modal_app.RETENTION_S` |

**CORS:** only browser origins listed in `MATHTTS_CORS_ORIGINS` at deploy
time, plus localhost dev ports (3000, 5173 and 8081 on `localhost`; 3000 and
5173 on `127.0.0.1`). Methods are `GET` and `POST`, and `Retry-After` is
exposed to scripts. Non-browser clients (curl, native apps) are not affected
by CORS.
