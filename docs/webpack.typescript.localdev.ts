// This webpack builds the examples, the library dist files are built with tsc
import path from 'path';
import webpack, {Configuration} from 'webpack';
import HtmlWebpackPlugin from 'html-webpack-plugin';
import ForkTsCheckerWebpackPlugin from 'fork-ts-checker-webpack-plugin';
import {TsconfigPathsPlugin} from 'tsconfig-paths-webpack-plugin';
import * as React from 'react';

const webpackConfig = (env): Configuration => {

    const conf: Configuration = {
      entry: './docs/examples/index-react18.tsx',
      //...(env.production || !env.development ? {} : {devtool: 'eval-source-map'}),
      devtool: 'eval-source-map',
      resolve: {
        alias: {
          'buckaroo': path.resolve(__dirname, '../js')
        },
        extensions: ['.ts', '.tsx', '.js'],
        //TODO waiting on https://github.com/dividab/tsconfig-paths-webpack-plugin/issues/61
        //@ts-ignore
        plugins: [new TsconfigPathsPlugin()]
      },
      output: {
        path: path.join(__dirname, '/build/html/examples'),
        filename: 'bundle.js'
      },
        // https://github.com/TypeStrong/ts-loader/issues/751
        ignoreWarnings: [{message: /export .* was not found in/}],
        module: {
            rules: [
                {
                    test: /\.tsx?$/,
                    loader: 'ts-loader',
                    options: {
                        transpileOnly: true,
                        configFile: 'docs/examples_tsconfig.json'
                    }
                },
		{
		    test: /\.css$/,
		    use: [
			//isDev ? 'style-loader' : MiniCssExtractPlugin.loader,
			'style-loader',
			'css-loader',
			{
			    loader: 'postcss-loader',
			    options: {
				postcssOptions: {
				    plugins: ['postcss-nested']
				}
			    }
			}
		    ]
		},
                {
                    test: /\.scss$/,
                    use: [
                        // We're in dev and want HMR, SCSS is handled in JS
                        // In production, we want our css as files
                        "style-loader",
                        "css-loader",
                        {
                            loader: "postcss-loader",
                            options: {
                                postcssOptions: {
                                    plugins: [
                                        ["postcss-preset-env"],
                                    ],
                                },
                            },
                        },
                        "sass-loader"
                    ],
                },
                {
                    test: /\.svg$/,
                    loader: 'svg-url-loader'
                },
                {
                    test: /\.md$/,
                    use: ['html-loader', 'markdown-loader']
                }
            ]
        },
        plugins: [
            new HtmlWebpackPlugin({
                template: './docs/examples/index.html'
            }),
            new webpack.DefinePlugin({
                process: {
                    env: {
                        DEBUG: !env.production || env.development
                    }
                },
                VERSION: JSON.stringify(require('../package.json').version),
                MAPBOX_TOKEN: JSON.stringify(process.env.MAPBOX_TOKEN)
            })
        ],
        devServer: {
            port: 8030
        }
    };


    // if (!env.development) {
    //     conf.plugins.push(
    //         new ForkTsCheckerWebpackPlugin({
    //             eslint: {
    //                 files: './{js,docs/examples}/**/*.{ts,tsx,js}'
    //             }
    //         })
    //     );
    // }


    return conf;
};

export default webpackConfig;
