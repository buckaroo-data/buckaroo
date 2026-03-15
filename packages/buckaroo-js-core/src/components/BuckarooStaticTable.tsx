import { useState, useEffect } from "react";
import { DFData, DFViewerConfig, DFDataOrPayload } from "./DFViewerParts/DFWhole";
import { resolveDFDataAsync } from "./DFViewerParts/resolveDFData";
import { DFViewer } from "./DFViewerParts/DFViewerInfinite";

export interface BuckarooArtifact {
    df_data: DFDataOrPayload;
    df_viewer_config: DFViewerConfig;
    summary_stats_data: DFDataOrPayload;
}

/**
 * Static table component for rendering a pre-computed buckaroo artifact.
 *
 * Both df_data and summary_stats_data may be parquet_b64 tagged payloads;
 * this component resolves them asynchronously before rendering.
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

    return (
        <DFViewer
            df_data={dfData}
            df_viewer_config={artifact.df_viewer_config}
            summary_stats_data={summaryStats}
        />
    );
}
