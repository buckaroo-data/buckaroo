import React, { useState } from "react";
import _ from "lodash";
import { OperationResult } from "./DependentTabs";
import { ColumnsEditor } from "./ColumnsEditor";

import { DFDataOrPayload } from "./DFViewerParts/DFWhole";
import { resolveDFData } from "./DFViewerParts/resolveDFData";
import { DFViewer } from "./DFViewerParts/DFViewerInfinite";
import { StatusBar } from "./StatusBar";
import { BuckarooState } from "./WidgetTypes";
import { BuckarooOptions } from "./WidgetTypes";
import { DFMeta } from "./WidgetTypes";
import { CommandConfigT } from "./CommandUtils";
import { Operation } from "./OperationUtils";
import { IDisplayArgs } from "./DFViewerParts/gridUtils";

export function WidgetDCFCell({
    df_data_dict,
    df_display_args,
    df_meta,
    operations,
    on_operations,
    operation_results,
    command_config,
    buckaroo_state,
    on_buckaroo_state,
    buckaroo_options,
}: {
    df_meta: DFMeta;
    df_data_dict: Record<string, DFDataOrPayload>;
    df_display_args: Record<string, IDisplayArgs>;
    operations: Operation[];
    on_operations: (ops: Operation[]) => void;
    operation_results: OperationResult;
    command_config: CommandConfigT;
    buckaroo_state: BuckarooState;
    on_buckaroo_state: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckaroo_options: BuckarooOptions;
}) {
  const [activeCol, setActiveCol] = useState<[string, string]>(["a", "stoptime"]);

    const cDisp = df_display_args[buckaroo_state.df_display];
    if (cDisp === undefined) {
        console.log("cDisp undefined", buckaroo_state.df_display, buckaroo_options.df_display);
    } else {
        //  console.log("cDisp", cDisp);
    }
    const dfData = resolveDFData(df_data_dict[cDisp.data_key]);
    const summaryStatsData = resolveDFData(df_data_dict[cDisp.summary_stats_key]);

    return (
        <div className="dcf-root flex flex-col buckaroo-widget" style={{ width: "100%", height: "100%" }}>
            <div
                className="orig-df"
                style={{
                    // height: '450px',
                    overflow: "hidden",
                }}
            >
                <StatusBar
                    dfMeta={df_meta}
                    buckarooState={buckaroo_state}
                    setBuckarooState={on_buckaroo_state}
                    buckarooOptions={buckaroo_options}
                    themeConfig={cDisp.df_viewer_config?.component_config?.theme}
                />
                <DFViewer
                    df_data={dfData}
                    df_viewer_config={cDisp.df_viewer_config}
                    summary_stats_data={summaryStatsData}
                    activeCol={activeCol}
                    setActiveCol={setActiveCol}
                />
            </div>
            {buckaroo_state.show_commands ? (
                <ColumnsEditor
                    df_viewer_config={cDisp.df_viewer_config}
                    activeColumn={activeCol}
                    operations={operations}
                    setOperations={on_operations}
                    operation_result={operation_results}
                    command_config={command_config}
                />
            ) : (
                <span></span>
            )}
        </div>
    );
}
