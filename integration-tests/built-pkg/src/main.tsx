import React from "react";
import { createRoot } from "react-dom/client";

// IMPORTANT: this import resolves through the installed npm tarball
// (./buckaroo-js-core.tgz, declared in package.json), NOT through the
// pnpm workspace. If this directory ever got pulled into the workspace
// and the import resolved to packages/buckaroo-js-core/src, this test
// would silently degrade to testing source. See README for guard rails.
import { DFViewer } from "buckaroo-js-core";
// CSS subpath (works pre-#721 via plain subpath access; post-#721 via exports).
import "buckaroo-js-core/dist/style.css";

const rows = [
  { index: 0, label: "alpha", value: 11 },
  { index: 1, label: "beta", value: 22 },
  { index: 2, label: "gamma", value: 33 },
];

const config = {
  pinned_rows: [],
  left_col_configs: [
    { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" as const } },
  ],
  column_config: [
    { col_name: "label", header_name: "label", displayer_args: { displayer: "obj" as const } },
    { col_name: "value", header_name: "value", displayer_args: { displayer: "obj" as const } },
  ],
};

function App() {
  return (
    <div style={{ padding: 16, height: 480 }}>
      <h1 data-testid="page-title">buckaroo-js-core (built tarball)</h1>
      <div style={{ height: 400 }}>
        <DFViewer df_data={rows} df_viewer_config={config} />
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
