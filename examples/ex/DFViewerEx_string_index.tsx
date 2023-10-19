import {DFViewer} from '../../js/components/DFViewer';
import { stringIndexDf } from '../../js/components/staticData';
import React, { useState} from 'react';


export default function Simple() {
    const [activeCol, setActiveCol] = useState('tripduration');
    return <DFViewer df={stringIndexDf} activeCol={activeCol} setActiveCol={setActiveCol} />;
}
