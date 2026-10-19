// After `expo export --platform web`: checks that dist/ will work on Cloudflare Pages.
//
// 1. Pages does not upload directories named node_modules. Package assets are
//    published under assets/vendor/ (scripts/pages-asset-plugin.js); fail if
//    anything still ends up under a node_modules directory, because on Pages its
//    URL would fall through to index.html (that is how the fonts went missing).
// 2. A top-level dist/404.html would turn off Pages' SPA fallback (index.html
//    for unknown paths), so refreshing /result/<id> would 404. Fail if one exists.
const fs = require('fs');
const path = require('path');

const dist = path.join(__dirname, '..', 'dist');

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? files(p) : [p];
  });
}

const all = files(dist);
const hidden = all.filter((p) => p.split(path.sep).includes('node_modules'));
if (hidden.length) {
  console.error(`pages-postbuild: under a node_modules directory, which Pages won't upload:\n  ${hidden.join('\n  ')}`);
  process.exit(1);
}
const refs = all.filter((p) => p.endsWith('.js') && fs.readFileSync(p, 'utf8').includes('/assets/node_modules/'));
if (refs.length) {
  console.error(`pages-postbuild: bundles still reference /assets/node_modules/:\n  ${refs.join('\n  ')}`);
  process.exit(1);
}
if (fs.existsSync(path.join(dist, '404.html'))) {
  console.error('pages-postbuild: dist/404.html would turn off Cloudflare Pages SPA routing');
  process.exit(1);
}
console.log('pages-postbuild: ok');
