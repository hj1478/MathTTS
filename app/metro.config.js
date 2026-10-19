// Learn more: https://docs.expo.dev/guides/customizing-metro
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// Publish package assets under /assets/vendor/ (scripts/pages-asset-plugin.js).
config.transformer.assetPlugins = [
  ...(config.transformer.assetPlugins ?? []),
  require.resolve('./scripts/pages-asset-plugin'),
];

module.exports = config;
