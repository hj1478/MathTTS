// Metro asset plugin (metro.config.js), for the Cloudflare Pages web export.
//
// Expo exports a package's assets (the IBM Plex Sans KR fonts, expo-router's
// icons) to dist/assets/node_modules/..., at the URL the bundle asks for. Pages
// does not upload directories named node_modules, so on Pages those URLs fell
// through to index.html and the fonts never loaded. Publishing them under
// /assets/vendor/ instead moves both the file and the URL: the export writes
// each asset to its httpServerLocation. Because the URLs inside the bundles
// change, the bundles get new hashed names too, so nothing stale stays cached.
// The location looks like /assets?export_path=/assets/node_modules/<pkg>/...;
// only the export_path part decides the exported file and its URL. The dev
// server finds assets by their source path, so development is unaffected.
const FROM = 'export_path=/assets/node_modules/';
const TO = 'export_path=/assets/vendor/';

module.exports = function pagesAssetPlugin(asset) {
  asset.httpServerLocation = asset.httpServerLocation.replace(FROM, TO);
  return asset;
};
