import React from 'react';
import { DFViewer } from './DFViewer';
import { DFWhole } from './DFWhole';
import { ITooltipParams } from 'ag-grid-community';

export function getBakedDFViewer(seriesDf: DFWhole) {
  const retFunc = (props: ITooltipParams) => {
    return (
      <div>
        <h1> series_summary </h1>
        <DFViewer
          df_data={seriesDf.data}
          df_viewer_config={seriesDf.dfviewer_config}
          summary_stats_data={[]}
        ></DFViewer>
      </div>
    );
  };
  return retFunc;
}
