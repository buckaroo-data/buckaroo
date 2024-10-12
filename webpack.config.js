const path = require('path');
const version = require('./package.json').version;
//import {TsconfigPathsPlugin} from 'tsconfig-paths-webpack-plugin';
const TsconfigPathsPlugin = require('tsconfig-paths-webpack-plugin');

//import HtmlWebpackPlugin from 'html-webpack-plugin';
const HtmlWebpackPlugin = require('html-webpack-plugin');
const luminoThemeImages = /^.*@lumino\/default-theme.*.png$/;

const crypto = require('crypto');

// Workaround for loaders using "md4" by default, which is not supported in FIPS-compliant OpenSSL
const cryptoOrigCreateHash = crypto.createHash;
crypto.createHash = (algorithm) =>
  cryptoOrigCreateHash(algorithm == 'md4' ? 'sha256' : algorithm);

const performance = {
  maxAssetSize: 100_000_000,
};

// Custom webpack rules
const rules = [
  { test: /\.tsx?$/, loader: 'ts-loader' },
  { test: /\.js$/, loader: 'source-map-loader' },
  { test: /\.css$/, use: ['style-loader', 'css-loader'] },
  {
    test: luminoThemeImages,
    issuer: /\.css$/,
    use: {
      loader: 'url-loader',
    },
  },
  {
    test: /\.(jpg|png|gif|woff|woff2)$/,
    exclude: luminoThemeImages,
    use: ['file-loader'],
  },
  {
    test: /\.md$/,
    use: ['html-loader', 'markdown-loader'],
  },
  {
    test: /\.svg(\?v=\d+\.\d+\.\d+)?$/,
    issuer: /\.css$/,
    use: {
      loader: 'svg-url-loader',
      options: { encoding: 'none', limit: 10000 },
    },
  },
];


// Packages that shouldn't be bundled but loaded at runtime
const externals = ['@jupyter-widgets/base'];

const resolve = {
  // Add '.ts' and '.tsx' as resolvable extensions.
  extensions: ['.webpack.js', '.web.js', '.ts', '.js', '.tsx'],
  plugins: [new TsconfigPathsPlugin()],
  fallback: { crypto: false },
};

module.exports = [
  /**
   * Embeddable buckaroo bundle
   *
   * This bundle is almost identical to the notebook extension bundle. The only
   * difference is in the configuration of the webpack public path for the
   * static assets.
   *
   * The target bundle is always `dist/index.js`, which is the path required by
   * the custom widget embedder.
   */
  {
    entry: './js/index.ts',
    output: {
      filename: 'index.js',
      path: path.resolve(__dirname, 'dist'),
      libraryTarget: 'amd',
      library: 'buckaroo',
      publicPath: 'https://unpkg.com/buckaroo@' + version + '/dist/',
    },
    devtool: 'source-map',
    module: {
      rules: rules,
    },
    externals,
    resolve,
    devServer: {
      port: 8030,
    },
    performance,
  },
];
