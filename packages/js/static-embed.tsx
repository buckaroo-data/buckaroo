import * as React from "react";
import * as ReactDOM from "react-dom/client";
import { BuckarooStaticTable, resolveDFDataAsync, preResolveDFDataDict } from "buckaroo-js-core";
import "../buckaroo-js-core/dist/style.css";

declare global {
    interface Window {
        __BUCKAROO_ARTIFACT__?: any;
    }
}

async function main() {
    const artifact = window.__BUCKAROO_ARTIFACT__;
    if (!artifact) {
        throw new Error("No __BUCKAROO_ARTIFACT__ found on window");
    }

    const rootEl = document.getElementById("root");
    if (!rootEl) throw new Error("No #root element found");

    // Pre-resolve parquet_b64 payloads before React render
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

    // For Buckaroo mode, pre-resolve all parquet_b64 values in df_data_dict
    if (artifact.embed_type === "Buckaroo" && artifact.df_data_dict) {
        resolved.df_display_args = artifact.df_display_args;
        resolved.df_data_dict = await preResolveDFDataDict(artifact.df_data_dict);
        // Ensure "main" key has the already-resolved data
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

main().catch((e) => {
    console.error("Buckaroo static embed init failed:", e);
    const rootEl = document.getElementById("root");
    if (rootEl) {
        rootEl.textContent = `Failed to render: ${e.message}`;
    }
});
