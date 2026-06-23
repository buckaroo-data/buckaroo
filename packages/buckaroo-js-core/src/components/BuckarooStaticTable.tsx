import { useState, useEffect, useMemo } from "react";
import { DFData, DFViewerConfig, DFDataOrPayload } from "./DFViewerParts/DFWhole";
import { decodeDFData, decodeDFDataDict } from "./DFViewerParts/resolveDFData";
import { DFViewer, DFViewerInfinite } from "./DFViewerParts/DFViewerInfinite";
import { StatusBar } from "./StatusBar";
import { BuckarooState, BuckarooOptions, DFMeta } from "./WidgetTypes";
import { IDisplayArgs } from "./DFViewerParts/gridUtils";

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
    const [dfDataDict, setDfDataDict] = useState<Record<string, DFData>>({});

    useEffect(() => {
        let cancelled = false;
        // Decode every envelope at this single ingestion edge so the
        // component tree below receives plain DFData end-to-end.
        Promise.all([
            decodeDFData(artifact.df_data),
            decodeDFData(artifact.summary_stats_data),
            decodeDFDataDict(artifact.df_data_dict),
        ]).then(([data, stats, dict]) => {
            if (!cancelled) {
                setDfData(data);
                setSummaryStats(stats);
                setDfDataDict(dict);
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
                dfDataDict={dfDataDict}
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
    dfDataDict,
    artifact,
}: {
    dfData: DFData;
    summaryStats: DFData;
    dfDataDict: Record<string, DFData>;
    artifact: BuckarooArtifact;
}) {
    const [buckarooState, setBuckarooState] = useState<BuckarooState>(artifact.buckaroo_state!);
    const [activeCol, setActiveCol] = useState<[string, string]>(["", ""]);

    const df_display_args = artifact.df_display_args!;

    const cDisp = df_display_args[buckarooState.df_display];

    const [dataWrapper, currentSummaryStats] = useMemo(() => {
        const dataKey = cDisp.data_key;
        const summaryKey = cDisp.summary_stats_key;

        // df_data_dict is already decoded (BuckarooStaticTable ran
        // decodeDFDataDict). For "main"/"all_stats" prefer the dedicated
        // pre-decoded props; otherwise look up the decoded dict.
        const data = dataKey === "main" ? dfData : (dfDataDict[dataKey] ?? []);
        const stats = summaryKey === "all_stats" ? summaryStats : (dfDataDict[summaryKey] ?? []);

        return [
            { data_type: "Raw" as const, data, length: data.length },
            stats,
        ];
    }, [buckarooState.df_display, cDisp, dfData, summaryStats, dfDataDict]);

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
                    themeConfig={cDisp.df_viewer_config?.component_config?.theme}
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
