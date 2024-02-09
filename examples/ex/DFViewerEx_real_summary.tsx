import {DFViewer} from '../../js/components/DFViewerParts/DFViewer';
//import { stringIndexDf } from '../../js/baked_data/staticData';
import React, { useState} from 'react';
//import { DFData, DFViewerConfig } from '../../js/components/DFViewerParts/DFWhole';
import { realSummaryConfig, realSummaryTableData } from '../../js/baked_data/staticData';


  export default function DFViewerExString() {
    const [activeCol, setActiveCol] = useState('tripduration');
    
        const current = {
          'df':realSummaryTableData, 'df_viewer_config': realSummaryConfig, 
          'summary_stats_data':realSummaryTableData };

    return <DFViewer df={current.df}
    df_viewer_config={current.df_viewer_config}
    summary_stats_data={current.summary_stats_data}
    activeCol={activeCol} setActiveCol={setActiveCol} />;
  }
  
