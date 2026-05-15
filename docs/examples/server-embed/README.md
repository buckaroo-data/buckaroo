# BuckarooServerView playground

Minimal Vite + React app that embeds a live Buckaroo server session via
`<BuckarooServerView>` from `buckaroo-js-core` — no iframe.

```
docs/examples/server-embed/
├── package.json     # buckaroo-js-core linked via link:../../../packages/buckaroo-js-core
├── index.html
├── vite.config.ts   # proxies /load + /ws/* → http://localhost:8700
├── tsconfig.json
└── src/
    ├── main.tsx
    ├── App.tsx     # dropdown of preset datasets → POST /load → render the view
    └── types.d.ts
```

The app has a dropdown of preset datasets. Pick one, hit **Load**, and
the app POSTs `/load` to the Buckaroo server (via the Vite proxy), then
opens a WebSocket session for it.

## One-time setup

Build the local `buckaroo-js-core` package — the example resolves it by
file path, so its `dist/` must exist.

```
cd packages/buckaroo-js-core && pnpm install && pnpm build
```

## Optional: download some bigger parquet files

The first preset (Citi Bike, April 2016) is bundled in the repo and works
out of the box. The other presets point at NYC TLC trip-data parquet
files that are *not* checked in. Download whichever you want to play
with — they're all from the same public TLC cloudfront bucket. Run from
the repo root:

```
mkdir -p docs/examples/server-embed/data
cd docs/examples/server-embed/data

# Yellow taxi, Jan 2024 — ~50 MB, ~3M rows
curl -L -O https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet

# Green taxi, Jan 2024 — ~1.4 MB, ~57k rows (small, useful sanity check)
curl -L -O https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2024-01.parquet

# For-hire vehicle high-volume, Jan 2024 — ~470 MB, ~20M rows
curl -L -O https://d37ci6vzurychx.cloudfront.net/trip-data/fhvhv_tripdata_2024-01.parquet
```

`data/` is gitignored — don't worry about checking these in by accident.
Browse the whole TLC archive at
<https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page> if you
want other months.

## Run it

Two terminals, both from the repo root:

```
# Terminal 1 — Buckaroo server
uv run python -m buckaroo.server --port 8700 --no-browser

# Terminal 2 — the example app
cd docs/examples/server-embed && pnpm install && pnpm dev
```

Open <http://localhost:5173>. Pick a dataset from the dropdown, hit
**Load**, and the embedded `<BuckarooServerView>` connects to that
session.

## How it works

- Vite proxies `/load` (HTTP) and `/ws/*` (WebSocket) to
  `http://localhost:8700`. The browser only ever talks to
  `localhost:5173`, so there's no CORS preflight on `/load`.
- The **Load** button does `fetch("/load", { method: "POST", … })` with
  the preset's `session` + `path` + `mode`. The server reads the file,
  creates/refreshes the session, and replies with metadata.
- `<BuckarooServerView wsUrl={…} />` then opens
  `ws://localhost:5173/ws/<session-id>`, which Vite proxies to the
  server's `/ws/<session-id>` endpoint.
- The server's `mode` decides which widget the React side renders:
  `"buckaroo"` for the full UI, `"viewer"` for plain DFViewer,
  `"lazy"` for polars LazyFrames.

## Pointing at a different server

```
BUCKAROO_SERVER=http://my-host:8700 pnpm dev
```

Vite picks that up at start time; nothing else needs to change.

## Tests

There's a Playwright integration test that boots a real Buckaroo server,
the example's Vite dev server, opens the page, clicks Load on the
bundled citibike preset, and asserts the grid renders. Run it:

```
cd docs/examples/server-embed
pnpm exec playwright install chromium    # one-time, ~150 MB
pnpm test
```

The Python server is started by `pw-tests/global-setup.ts` from the
repo root (so `uv run python -m buckaroo.server` finds the venv) and
torn down by `pw-tests/global-teardown.ts`. Vite is launched by
Playwright's own `webServer` config.
