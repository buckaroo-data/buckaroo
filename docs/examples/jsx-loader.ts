//import prettier from 'prettier/standalone';
const prettier = require('prettier/standalone')

//import parserTypescript from 'prettier/parser-typescript';
const parserTypescript = require('prettier/parser-typescript');
//import Prism from 'prismjs';
const Prism = require('prismjs');


import loadLanguages from 'prismjs/components/';
//const loadLanguages = require('prismjs/components');
loadLanguages(['tsx', 'jsx', 'typescript']);

export default function tsx_loader(content: string, map: unknown, meta: unknown): void {
    const formatted = prettier.format(content, {
        parser: 'typescript',
        plugins: [parserTypescript]
    });
    const html = Prism.highlight(formatted, Prism.languages.tsx, 'tsx');
    this.callback(null, html, map, meta);
    return;
}
