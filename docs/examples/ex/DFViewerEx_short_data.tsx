import React, { useState} from 'react';
import { bakedData, extraComponents } from 'buckaroo';



  export default function DFViewerExString() {
    const [activeCol, setActiveCol] = useState('tripduration');
//    const dfv_config:DFViewerConfig = {
    const dfv_config:any = {
      column_config:   bakedData.realSummaryConfig.column_config,
      pinned_rows: []}

        const current = {
          'df':bakedData.realSummaryTableData, 'df_viewer_config': bakedData.realSummaryConfig, 
          'summary_stats_data': bakedData.realSummaryTableData };

    return <extraComponents.DFViewer df_data={current.df.slice(0,3)}
    df_viewer_config={dfv_config}
    summary_stats_data={[]}
    activeCol={activeCol} setActiveCol={setActiveCol} />;
  }
  
