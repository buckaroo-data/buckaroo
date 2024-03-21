import React, { useState} from 'react';
import { extraComponents, bakedData } from 'buckaroo';

//import { realSummaryConfig, realSummaryTableData } from '../../../js/baked_data/staticData';
//import { realSummaryConfig, realSummaryTableData } from 'buckaroo';


  export default function DFViewerExString() {
    const [activeCol, setActiveCol] = useState('tripduration');
    
        const current = {
          'df': bakedData.realSummaryTableData, 'df_viewer_config': bakedData.realSummaryConfig, 
          'summary_stats_data': bakedData.realSummaryTableData };

    return <extraComponents.DFViewer df_data={current.df}
    df_viewer_config={current.df_viewer_config}
    summary_stats_data={current.summary_stats_data}
    activeCol={activeCol} setActiveCol={setActiveCol} />;
  }
  
