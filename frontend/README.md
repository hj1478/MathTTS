# MathTTS frontend

An Expo app (SDK 58, Expo Router) for the backend in `../backend`
(API: [`../docs/API.md`](../docs/API.md)). It is deployed as a static web
export on Cloudflare Pages, and the same code runs on iOS and Android.

The app has two routes:

- `/` lets the user take or pick a photo, re-encodes it as a JPEG of at most
  2400 px (which handles both the 5 MB limit and HEIC), and calls `POST /jobs`.
- `/jobs/[id]` polls `GET /jobs/{id}` and shows the result. Because the job id
  is in the URL, a refresh resumes the same job.

## How it uses the backend

| Requirement | Where |
|---|---|
| `POST /warmup` as soon as the app or page opens, and again when it returns to the foreground after 60 s or more | `src/app/_layout.tsx` |
| Poll every 0.5 s, start to start, with no overlapping requests | `src/lib/use-job.ts` |
| OCR text and spoken text shown as soon as they arrive | `src/app/jobs/[id].tsx` |
| MP3 playback from `audio.url` | `src/components/audio-player.tsx` (expo-audio) |
| While queued: elapsed time plus a Korean "server is starting" message. Gives up after 10 min, with a retry button | `src/app/jobs/[id].tsx`, `GIVE_UP_AFTER_S` |

Elapsed time is counted from the job's `created_at`, so it survives a refresh.
This assumes the device clock is roughly correct. Retry re-uploads the last
photo, which is kept in memory only. After a refresh, the retry button sends the
user back to pick the photo again.

## Develop

```sh
npm install
cp .env.example .env        # EXPO_PUBLIC_API_URL, the backend base URL
npm run web                 # http://localhost:8081, already allowed by the backend's CORS
npm run typecheck && npm run lint
```

## Deploy: Cloudflare Pages

Connect the repository to Pages and use these settings:

| Setting | Value |
|---|---|
| Framework preset | None |
| Root directory | `frontend` |
| Build command | `npm run build:web` |
| Build output directory | `dist` |
| Environment variables | `EXPO_PUBLIC_API_URL` = the backend URL; `NODE_VERSION` = `22` |

`build:web` runs `expo export --platform web`. `app.json` sets `web.output:
"single"`, so the export is a single-page app: one `index.html`, plus `_headers`
copied from `public/`.

**Client-side routing.** When a Pages build has no top-level `404.html`, Pages
serves `index.html` for any path that is not a file, so refreshing
`/jobs/<id>` loads the app, which then reads the job id from the URL.
`build:web` fails if the export ever contains a `404.html`, because that would
turn this fallback off. Do not add a `_redirects` catch-all; it isn't needed.

**CORS.** The backend only accepts browser requests from the origins listed in
`MATHTTS_CORS_ORIGINS`. Redeploy it with the Pages origin(s) added:

```sh
MATHTTS_CORS_ORIGINS="https://<project>.pages.dev,https://<custom domain>" modal deploy backend/modal_app.py
```

The list is matched exactly. Preview deployments
(`https://<hash>.<project>.pages.dev`) are not covered unless each one is added.
