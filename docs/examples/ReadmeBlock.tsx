/* eslint-disable @typescript-eslint/ban-ts-comment */
import React from 'react';
// @ts-ignore
import READMEmd from '../../README.md';
//const READMEmd = "<h1> paddy readme</h1>"

// This is expensive to render
const ReadmeBlock = React.memo(function _README() {
    return <div dangerouslySetInnerHTML={{__html: READMEmd}} />;
});

export default ReadmeBlock;
