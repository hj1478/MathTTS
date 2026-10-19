# MathTTS UI design

Design mockups for the student-facing app (Expo, mobile + web). Live canvas:
https://claude.ai/artifact/G1pCMcc1d69qWdcT2aM3vc

These are `.dc.html` files for the canvas editor, not app code. They need the
editor's `support.js` runtime, so opening one directly in a browser won't
render it properly. Use them as the visual and spec reference.

- `canvas.json`: board layout and titles
- Mobile flow (390px): `Main`, `Crop`, `Processing`, `ProcessingFailed`,
  `Result`, `ResultDark`, `ResultLargeText`, `History`
- Error states: `QuotaReached`, `RateLimited`, `UploadTooLarge`,
  `UploadNotImage`, `Offline`, `NothingRecognized`
- Desktop (1280px): `DesktopHome`, `DesktopResult`
- Specs: `Components` (buttons, player, step indicator, banners, history row)
  and `Tokens` (colors with contrast ratios, type scale, spacing, focus
  order, screen-reader behaviour)

The canvas is the source of truth; re-export here after editing it.
