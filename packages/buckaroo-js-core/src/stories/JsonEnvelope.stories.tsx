import type { Meta, StoryObj } from "@storybook/react";
import { DFEnvelope, DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import { BuckarooStaticTable, BuckarooArtifact } from "../components/BuckarooStaticTable";

import "../style/dcf-npm.css";

// A `json` transport envelope — the inline record-array variant of DFEnvelope.
// Handing it to BuckarooStaticTable as artifact.df_data forces the component
// through its real ingestion edge (decodeDFData), exercising the `json`
// branch end-to-end into AG-Grid. No parquet, no Python — pure JS transport.
const jsonEnvelope: DFEnvelope = {
    format: "json",
    data: [
        { index: 0, a: "alpha", b: "foo" },
        { index: 1, a: "beta", b: "bar" },
    ],
};

const INDEX_COL_CONFIG: NormalColumnConfig = {
    col_name: "index",
    header_name: "index",
    displayer_args: { displayer: "string" },
};

const df_viewer_config: DFViewerConfig = {
    column_config: [
        { col_name: "a", header_name: "a", displayer_args: { displayer: "string" } },
        { col_name: "b", header_name: "b", displayer_args: { displayer: "string" } },
    ],
    pinned_rows: [],
    left_col_configs: [INDEX_COL_CONFIG],
};

const artifact: BuckarooArtifact = {
    df_data: jsonEnvelope,
    df_viewer_config,
    summary_stats_data: [],
};

const JsonEnvelopeWrap = () => (
    <div style={{ height: 500, width: 800 }}>
        <BuckarooStaticTable artifact={artifact} />
    </div>
);

const meta = {
    title: "Buckaroo/Transport/JsonEnvelope",
    component: JsonEnvelopeWrap,
    parameters: { layout: "centered" },
} satisfies Meta<typeof JsonEnvelopeWrap>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
