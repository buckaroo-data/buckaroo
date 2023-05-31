import {DFViewer} from '../../js/components/DFViewer';
import {tableDf } from '../../js/components/staticData';
import React, { useState} from 'react';


export default function Simple() {
    const [activeCol, setActiveCol] = useState('tripduration');
    return <DFViewer df={tableDf} activeCol={activeCol} setActiveCol={setActiveCol} />;
}
