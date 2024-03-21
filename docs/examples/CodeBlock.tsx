import React from 'react';
import CodePenButton from './CodePenButton';
import 'prism-themes/themes/prism-vsc-dark-plus.css';

// This is expensive to render
const CodeBlock = React.memo(function _CodeBlock(props: {
    title: string;
    code: Promise<string>;
    text: Promise<string>;
}) {
    const [code, setCode] = React.useState('loading()');
    React.useEffect(() => {
        props.code.then((r) => setCode(r));
    }, [props.code, props.text]);
    return (
        <div className='position-relative'>
            <CodePenButton title={props.title} text={props.text} />
            <div className='codeblock'>
                <pre className='p-2' style={{backgroundColor: 'rgb(43, 43, 43)', fontSize: '16px'}}>
                    <code className='language-tsx' dangerouslySetInnerHTML={{__html: code}} />
                </pre>
            </div>
        </div>
    );
});

export default CodeBlock;
