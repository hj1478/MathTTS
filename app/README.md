# MathTTS app

The student-facing client (Expo: iOS, Android and web), built from the mockups
in `../design/ui` and talking to the backend described in `../docs/API.md`.

```sh
npm install
npx expo start          # press w for web, or scan the QR code with Expo Go
```

The backend URL defaults to the deployed Modal app. Point it somewhere else
with `EXPO_PUBLIC_API_URL=https://<workspace>--mathtts-dev.<region>.modal.run`.
Web dev runs on `localhost:8081`, which the backend's CORS already allows; a
deployed web build needs its origin in `MATHTTS_CORS_ORIGINS`.

| Screen (`src/app/`) | Designs |
|---|---|
| `index.tsx` | Main, DesktopHome, UploadTooLarge, UploadNotImage, Offline |
| `crop.tsx` | Crop |
| `processing.tsx` | Processing, ProcessingFailed, RateLimited, NothingRecognized |
| `result/[id].tsx` | Result, ResultDark, ResultLargeText, DesktopResult, QuotaReached |
| `history.tsx` | History |

How it uses the API: `POST /warmup` when the app opens, the crop screen opens
and the home screen regains focus; `POST /jobs` with the cropped photo
(re-encoded as JPEG, at most 2400 px on the long side); `GET /jobs/{id}` every
0.5 s, showing the OCR text as soon as it arrives; the MP3 plays from
`audio.url`.

Notes:

- History is on-device only (AsyncStorage). On iOS/Android a saved result's
  photo and MP3 are copied into the app's documents. On web the photo is kept
  as a data URL, but the audio stays on the server, which deletes it after
  24 h. After that the result shows "음성 보관 기간이 지났어요" and offers to
  read it again.
- The "지금 읽는 부분" highlight is estimated from character counts, since the
  backend returns no word timings. Azure word-boundary events would make it
  exact.
- "읽은 문제" is typeset with KaTeX (in a WebView on native). Screen readers
  hear the spoken sentence instead of symbol names.
- `POST /warmup` goes through one throttle (`src/lib/api.ts`): at most once a
  minute, counting a job sent or answered as a warmup, and remembered across
  reloads and tabs on web. The worker stays up 90 s after its last request, so
  that is enough, and it spares the 30-an-hour per-IP budget that everyone
  behind one school network address shares. It is tried when the app opens,
  returns from the background, the home screen regains focus and the crop
  screen opens; the offline banner's "연결 다시 확인" always sends one.
- The current flow (picked photo, cropped photo, job id, the last 3 results)
  is kept in `sessionStorage` on web and AsyncStorage on native
  (`persistSession` in `src/lib/store.ts`), so a refresh continues it.

## Deploy: Cloudflare Pages

Connect the repository to Pages and use these settings:

| Setting | Value |
|---|---|
| Framework preset | None |
| Root directory | `app` |
| Build command | `npm run build:web` |
| Build output directory | `dist` |
| Environment variables | `NODE_VERSION` = `22`; optionally `EXPO_PUBLIC_API_URL` (defaults to the deployed backend) |

`build:web` runs `expo export --platform web`, then `scripts/pages-postbuild.js`.
`web.output` is `"single"`, so the export is a single-page app: one
`index.html`, hashed bundles and assets, and `_headers` (copied from `public/`).

**Fonts.** Pages does not upload directories named `node_modules`, and Expo
exports package assets, including the IBM Plex Sans KR font files, under
`dist/assets/node_modules/`. Deployed as is, those URLs fall through to
`index.html`, the fonts never load, and the text renders in the browser's
default serif. `pages-postbuild.js` moves them to `dist/assets/vendor/` and
rewrites the references, and fails the build if anything is still under a
`node_modules` directory. `_headers` caches the hashed files for a
year and never caches `index.html`, so a new deploy shows up on the next load.

**Client-side routing.** When the build output has no top-level `404.html`,
Pages serves `index.html` for any path that isn't a file. So refreshing
`/result/<id>`, `/history` or any other route loads the app instead of
returning a 404. The build fails if the export ever contains a `404.html`,
because that would turn this fallback off. Don't add a `_redirects` catch-all;
it isn't needed. On a refresh:

- `/crop` shows the same photo (unless the original was too big to keep, in
  which case it goes home);
- `/processing?job=<id>` keeps polling the same job instead of sending the
  photo again;
- `/result/<id>` shows the result, saved or not.

`/jobs/<id>` opens any job by its id, also on another device, for the 24 h the
server keeps it: it polls the job if it is still running, then shows the
result without the photo. An unknown id shows the server's Korean "작업을 찾을
수 없습니다" message.

**CORS.** The backend accepts browser requests only from origins listed in
`MATHTTS_CORS_ORIGINS`. Redeploy it with the Pages origin(s):

```sh
MATHTTS_CORS_ORIGINS="https://<project>.pages.dev,https://<custom domain>" modal deploy backend/modal_app.py
```

The list is matched exactly, so preview deployments
(`https://<hash>.<project>.pages.dev`) need their own entries.
