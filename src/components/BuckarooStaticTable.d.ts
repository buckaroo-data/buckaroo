import { DFViewerConfig, DFDataOrPayload } from './DFViewerParts/DFWhole';
import { BuckarooState, BuckarooOptions, DFMeta } from './WidgetTypes';
import { IDisplayArgs } from './DFViewerParts/gridUtils';
export interface BuckarooArtifact {
    embed_type?: "DFViewer" | "Buckaroo";
    df_data: DFDataOrPayload;
    df_viewer_config: DFViewerConfig;
    summary_stats_data: DFDataOrPayload;
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
export declare function BuckarooStaticTable({ artifact }: {
    artifact: BuckarooArtifact;
}): import("react/jsx-runtime").JSX.Element;
