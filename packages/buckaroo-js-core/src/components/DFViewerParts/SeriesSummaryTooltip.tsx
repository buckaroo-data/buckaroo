import { DFViewer } from "./DFViewer";
import { DFWhole } from "./DFWhole";
import { ITooltipParams } from "@ag-grid-community/core";

export function getBakedDFViewer(seriesDf: DFWhole) {
    const retFunc = (_props: ITooltipParams) => {
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
export const simpleTooltip = (props: ITooltipParams) => {
    // displaying the tooltip for histograms is distracting.
    // This should be possible with the tooltipValueGetter, but that
    // wasn't working for some reason

    // console.log("simpleTooltip props", props);
    // console.log("props.colId", props.column.colId, "pinned",
    // 		props.column.pinned, "node.id", props.node.id, "rowIndex", props.rowIndex)
    if (props.data.index === "histogram") {
        return;
    }
    return <div className="ag-tooltip">{props.valueFormatted}</div>;
};
