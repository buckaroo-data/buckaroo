import {DFViewer} from '../../js/components/DFViewerParts/DFViewer';
//import { stringIndexDf } from '../../js/baked_data/staticData';
import React, { useState} from 'react';
//import { DFData, DFViewerConfig } from '../../js/components/DFViewerParts/DFWhole';
import { realSummaryConfig, realSummaryTableData } from '../../js/baked_data/staticData';
import { DFViewerConfig } from '../../js/components/DFViewerParts/DFWhole';


  export default function DFViewerExString() {
    const [activeCol, setActiveCol] = useState('tripduration');
    const dfv_config:DFViewerConfig = {
      column_config:   realSummaryConfig.column_config,
      pinned_rows: []}

        const current = {
          'df':realSummaryTableData, 'df_viewer_config': realSummaryConfig, 
          'summary_stats_data':realSummaryTableData };

    return <DFViewer df_data={current.df.slice(0,3)}
    df_viewer_config={dfv_config}
    summary_stats_data={[]}
    activeCol={activeCol} setActiveCol={setActiveCol} />;
  }
  
