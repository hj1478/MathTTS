// After `expo export --platform web`: make dist/ deployable on Cloudflare Pages.
//
// 1. Pages does not upload directories named node_modules, and Expo exports
//    package assets (the IBM Plex Sans KR fonts, expo-router's icons) under
//    dist/assets/node_modules/. On Pages those URLs fell through to index.html,
//    so the fonts never loaded. Move the files to dist/assets/vendor/ and add a
//    Pages rewrite (_redirects, status 200) from the old URLs to the new place.
//    The bundles are left byte-for-byte as Expo built them: their file names
//    carry a hash of their contents and _headers caches them for a year, so
//    editing a bundle without renaming it would leave browsers on the old copy.
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
  const rule = '/assets/node_modules/* /assets/vendor/:splat 200\n';
  const redirects = path.join(dist, '_redirects');
  const existing = fs.existsSync(redirects) ? fs.readFileSync(redirects, 'utf8') : '';
  if (!existing.includes(rule)) fs.writeFileSync(redirects, rule + existing);
  console.log('pages-postbuild: assets/node_modules -> assets/vendor, rewrite added to _redirects');
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
