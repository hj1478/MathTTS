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
