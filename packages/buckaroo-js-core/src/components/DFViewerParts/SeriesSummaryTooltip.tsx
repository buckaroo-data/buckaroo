import { DFViewer } from "./DFViewerInfinite";
import { DFWhole, TooltipConfig } from "./DFWhole";
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
export const getSimpleTooltip = (tooltipField:string) => {
    
    const simpleTooltip = (props: ITooltipParams) => {
    	// displaying the tooltip for histograms is distracting.
    	// This should be possible with the tooltipValueGetter, but that
	    // wasn't working for some reason

    	if (props.data.index === "histogram") {
            return;
	    }
    	const val = props.data[tooltipField].toString()
	    return <div className="ag-tooltip">{val}</div>;
    };
    return simpleTooltip;
}

interface RealTooltipParams {
    tooltipField:string;
    tooltipComponent: (props:ITooltipParams) => React.Component
}
interface EmptyTooltipParams {}

export type CDTooltipParams = RealTooltipParams|EmptyTooltipParams

export const getTooltipParams = (
    //single_series_summary_df: DFWhole,
     tooltip_config?: TooltipConfig): CDTooltipParams => {
    if (tooltip_config === undefined) {
        return {}
    }
    switch (tooltip_config.tooltip_type) {
        case "simple":
            return {
                tooltipComponent: getSimpleTooltip(tooltip_config.val_column),
                tooltipField: tooltip_config.val_column
            };
        case "summary_series":
            return {};
            // return {
            //     tooltipComponent: getBakedDFViewer(single_series_summary_df),
            //     tooltipField: "index",
            //     tooltipComponentParams: {},
            // };

    }
}

