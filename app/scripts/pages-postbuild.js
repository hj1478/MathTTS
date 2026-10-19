// After `expo export --platform web`: make dist/ deployable on Cloudflare Pages.
//
// 1. Pages does not upload directories named node_modules, and Expo exports
//    package assets (the IBM Plex Sans KR fonts, expo-router's icons) under
//    dist/assets/node_modules/. On Pages those URLs fall through to index.html,
//    so the fonts never load. Move them to dist/assets/vendor/ and rewrite the
//    references in the exported files.
// 2. A top-level dist/404.html would turn off Pages' SPA fallback (index.html
//    for unknown paths), so refreshing /result/<id> would 404. Fail if one exists.
const fs = require('fs');
const path = require('path');

const dist = path.join(__dirname, '..', 'dist');
const from = path.join(dist, 'assets', 'node_modules');
const to = path.join(dist, 'assets', 'vendor');

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? files(p) : [p];
  });
}

if (fs.existsSync(from)) {
  fs.rmSync(to, { recursive: true, force: true });
  fs.renameSync(from, to);
  let rewritten = 0;
  for (const f of files(dist).filter((p) => /\.(js|html|css|json|map)$/.test(p))) {
    const s = fs.readFileSync(f, 'utf8');
    if (s.includes('/assets/node_modules/')) {
      fs.writeFileSync(f, s.split('/assets/node_modules/').join('/assets/vendor/'));
      rewritten++;
    }
  }
  console.log(`pages-postbuild: assets/node_modules -> assets/vendor (${rewritten} file(s) rewritten)`);
}

const left = files(dist).filter((p) => p.split(path.sep).includes('node_modules'));
if (left.length) {
  console.error(`pages-postbuild: still under a node_modules directory, Pages won't upload:\n  ${left.join('\n  ')}`);
  process.exit(1);
}
if (fs.existsSync(path.join(dist, '404.html'))) {
  console.error('pages-postbuild: dist/404.html would turn off Cloudflare Pages SPA routing');
  process.exit(1);
}
