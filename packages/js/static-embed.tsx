import * as React from "react";
import * as ReactDOM from "react-dom/client";
import { BuckarooStaticTable, resolveDFDataAsync, preResolveDFDataDict } from "buckaroo-js-core";
import "../buckaroo-js-core/dist/style.css";

// Named exports so callers can import parquetRead from static-embed.js directly
// and feed raw ArrayBuffer parquet (e.g. from fetch()) without base64 encoding.
// Re-exported via buckaroo-js-core (which re-exports from hyparquet) to keep a
// single source of truth for the parquet decoder.
export { parquetRead, parquetMetadata, resolveDFDataAsync, preResolveDFDataDict } from "buckaroo-js-core";

// Resolve any parquet_b64 payloads in the artifact and render it into rootEl.
// Exported so callers that fetch raw parquet (via the exported parquetRead)
// can build an artifact at runtime and trigger the same render main() does.
export async function renderArtifact(rootEl: HTMLElement, artifact: any) {
    const [dfData, summaryStatsData] = await Promise.all([
        resolveDFDataAsync(artifact.df_data),
        resolveDFDataAsync(artifact.summary_stats_data),
    ]);

    const resolved: any = {
        embed_type: artifact.embed_type || "DFViewer",
        df_data: dfData,
        df_viewer_config: artifact.df_viewer_config,
        summary_stats_data: summaryStatsData,
    };

    if (artifact.embed_type === "Buckaroo" && artifact.df_data_dict) {
        resolved.df_display_args = artifact.df_display_args;
        resolved.df_data_dict = await preResolveDFDataDict(artifact.df_data_dict);
        resolved.df_data_dict["main"] = dfData;
        resolved.df_meta = artifact.df_meta;
        resolved.buckaroo_options = artifact.buckaroo_options;
        resolved.buckaroo_state = artifact.buckaroo_state;
    }

    const root = ReactDOM.createRoot(rootEl);
    root.render(
        <div className="buckaroo_anywidget" style={{ width: "100%", height: "100vh" }}>
            <BuckarooStaticTable artifact={resolved} />
        </div>
    );
}

async function main() {
    const dataEl = document.getElementById("buckaroo-data");
    // When the bundle is imported purely as a library (for parquetRead / renderArtifact),
    // there is no #buckaroo-data; silently skip auto-init instead of erroring.
    if (!dataEl?.textContent) return;
    const rootEl = document.getElementById("root");
    if (!rootEl) throw new Error("No #root element found");
    await renderArtifact(rootEl, JSON.parse(dataEl.textContent));
}

main().catch((e) => {
    console.error("Buckaroo static embed init failed:", e);
    const rootEl = document.getElementById("root");
    if (rootEl) {
        rootEl.textContent = `Failed to render: ${e.message}`;
    }
});
