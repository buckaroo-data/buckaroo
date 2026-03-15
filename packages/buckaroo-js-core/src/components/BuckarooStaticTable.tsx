import { useState, useEffect, useMemo } from "react";
import { DFData, DFViewerConfig, DFDataOrPayload } from "./DFViewerParts/DFWhole";
import { resolveDFDataAsync } from "./DFViewerParts/resolveDFData";
import { DFViewer, DFViewerInfinite } from "./DFViewerParts/DFViewerInfinite";
import { StatusBar } from "./StatusBar";
import { BuckarooState, BuckarooOptions, DFMeta } from "./WidgetTypes";
import { IDisplayArgs } from "./DFViewerParts/gridUtils";
import { resolveDFData } from "./DFViewerParts/resolveDFData";

export interface BuckarooArtifact {
    embed_type?: "DFViewer" | "Buckaroo";
    df_data: DFDataOrPayload;
    df_viewer_config: DFViewerConfig;
    summary_stats_data: DFDataOrPayload;
    // Buckaroo mode fields
    df_display_args?: Record<string, IDisplayArgs>;
    df_data_dict?: Record<string, DFDataOrPayload>;
    df_meta?: DFMeta;
    buckaroo_options?: BuckarooOptions;
    buckaroo_state?: BuckarooState;
}

/**
 * Static table component for rendering a pre-computed buckaroo artifact.
 *
 * Both df_data and summary_stats_data may be parquet_b64 tagged payloads;
 * this component resolves them asynchronously before rendering.
 *
 * When embed_type is "Buckaroo", renders with StatusBar for switching
 * between main/summary_stats displays.
 */
export function BuckarooStaticTable({ artifact }: { artifact: BuckarooArtifact }) {
    const [dfData, setDfData] = useState<DFData | null>(null);
    const [summaryStats, setSummaryStats] = useState<DFData | null>(null);

    useEffect(() => {
        let cancelled = false;
        Promise.all([
            resolveDFDataAsync(artifact.df_data),
            resolveDFDataAsync(artifact.summary_stats_data),
        ]).then(([data, stats]) => {
            if (!cancelled) {
                setDfData(data);
                setSummaryStats(stats);
            }
        });
        return () => { cancelled = true; };
    }, [artifact]);

    if (dfData === null || summaryStats === null) {
        return <div style={{ padding: 20, fontFamily: "sans-serif" }}>Loading...</div>;
    }

    if (artifact.embed_type === "Buckaroo" && artifact.df_display_args && artifact.df_data_dict && artifact.df_meta && artifact.buckaroo_options && artifact.buckaroo_state) {
        return (
            <BuckarooStaticWidget
                dfData={dfData}
                summaryStats={summaryStats}
                artifact={artifact}
            />
        );
    }

    return (
        <DFViewer
            df_data={dfData}
            df_viewer_config={artifact.df_viewer_config}
            summary_stats_data={summaryStats}
        />
    );
}

function BuckarooStaticWidget({
    dfData,
    summaryStats,
    artifact,
}: {
    dfData: DFData;
    summaryStats: DFData;
    artifact: BuckarooArtifact;
}) {
    const [buckarooState, setBuckarooState] = useState<BuckarooState>(artifact.buckaroo_state!);
    const [activeCol, setActiveCol] = useState<[string, string]>(["", ""]);

    const df_display_args = artifact.df_display_args!;
    const df_data_dict = artifact.df_data_dict!;

    const cDisp = df_display_args[buckarooState.df_display];

    const [dataWrapper, currentSummaryStats] = useMemo(() => {
        const dataKey = cDisp.data_key;
        const summaryKey = cDisp.summary_stats_key;

        // For "main" key, use the pre-resolved dfData; otherwise resolve from dict
        const data = dataKey === "main" ? dfData : resolveDFData(df_data_dict[dataKey]);
        const stats = summaryKey === "all_stats" ? summaryStats : resolveDFData(df_data_dict[summaryKey]);

        return [
            { data_type: "Raw" as const, data, length: data.length },
            stats,
        ];
    }, [buckarooState.df_display, cDisp, dfData, summaryStats, df_data_dict]);

    return (
        <div className="dcf-root flex flex-col buckaroo-widget buckaroo-infinite-widget"
            style={{ width: "100%", height: "100%" }}>
            <div
                className="orig-df flex flex-row"
                style={{ overflow: "hidden" }}
            >
                <StatusBar
                    dfMeta={artifact.df_meta!}
                    buckarooState={buckarooState}
                    setBuckarooState={setBuckarooState}
                    buckarooOptions={artifact.buckaroo_options!}
                />
                <DFViewerInfinite
                    data_wrapper={dataWrapper}
                    df_viewer_config={cDisp.df_viewer_config}
                    summary_stats_data={currentSummaryStats}
                    activeCol={activeCol}
                    setActiveCol={setActiveCol}
                />
            </div>
        </div>
    );
}
