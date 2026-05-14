# BuckarooServerView playground

Minimal Vite + React app that embeds a live Buckaroo server session via
`<BuckarooServerView>` from `buckaroo-js-core` — no iframe.

```
docs/examples/server-embed/
├── package.json    # buckaroo-js-core linked via file:../../../packages/buckaroo-js-core
├── index.html
├── vite.config.ts
└── src/
    ├── main.tsx
    └── App.tsx    # input boxes for server URL + session id; renders the view
```

## One-time setup

Build the local `buckaroo-js-core` package — the example resolves it by file path,
so its `dist/` must exist.

```
cd packages/buckaroo-js-core && pnpm install && pnpm build
```

## Run it

Three terminals. From the repo root:

### 1. Start the Buckaroo server

```
uv run python -m buckaroo.server --port 8700 --no-browser
```

### 2. Load a session

Any file path the server can read works. The repo ships a sample parquet:

```
curl -X POST http://localhost:8700/load \
  -H 'Content-Type: application/json' \
  -d '{"session":"demo","path":"docs/example-notebooks/citibike-trips-2016-04.parq","mode":"buckaroo","no_browser":true}'
```

`mode` picks the widget the React side renders:

- `"buckaroo"` → full UI (status bar, summary stats, search, post-processing)
- `"viewer"`  → just the infinite-scroll DFViewer
- `"lazy"`    → polars LazyFrame, pushes ops to polars

### 3. Start the example app

```
cd docs/examples/server-embed
pnpm install
pnpm dev
```

Open <http://localhost:5173>. The top bar lets you point at any server URL
and session id — change them, hit **Connect**, and `<BuckarooServerView>`
reconnects.

## Loading more sessions

POST another session and switch to it in the UI:

```
curl -X POST http://localhost:8700/load \
  -H 'Content-Type: application/json' \
  -d '{"session":"grease","path":"docs/example-notebooks/grease_violations.csv","mode":"viewer","no_browser":true}'
```

Then type `grease` into the Session box and click Connect.

## What's happening

`BuckarooServerView` opens a WebSocket to `ws://<host>/ws/<session-id>`,
waits for the server's `initial_state` frame, decodes the embedded parquet,
and renders `BuckarooInfiniteWidget` or `DFViewerInfiniteDS` based on the
session's `mode`. Sort, search, infinite scroll, and post-processing all
flow through the same WebSocket — same as the standalone server page,
just rendered inline in your React tree.
