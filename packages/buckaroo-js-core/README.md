# buckaroo-js-core

React + AG-Grid components and the infinite-scroll data layer that power the [Buckaroo](https://github.com/paddymul/buckaroo) DataFrame viewer.

This package is the framework-agnostic JS half of Buckaroo. The Python widget side ships it bundled inside `buckaroo` on PyPI; you only need to install this package directly if you are:

- embedding the DataFrame viewer in a React app outside Jupyter (e.g. a SPA),
- building a custom widget shell against a different host, or
- developing Buckaroo itself.

## Install

```sh
npm install buckaroo-js-core
# or
pnpm add buckaroo-js-core
# or
yarn add buckaroo-js-core
```

React 18 is a peer dependency.

## Usage

```tsx
import { DFViewer } from "buckaroo-js-core";
import "buckaroo-js-core/style.css";

export function App() {
  return (
    <DFViewer
      df_data={[{ index: 0, a: 1 }, { index: 1, a: 2 }]}
      df_viewer_config={{
        pinned_rows: [],
        left_col_configs: [],
        column_config: [
          { col_name: "index", header_name: "index", displayer_args: { displayer: "obj" } },
          { col_name: "a",     header_name: "a",     displayer_args: { displayer: "obj" } },
        ],
      }}
    />
  );
}
```

Higher-level components are also exported:

- `DFViewer` — render a static array of rows
- `DFViewerInfinite` — infinite-scroll grid backed by an AG-Grid datasource
- `DFViewerInfiniteDS` — datasource-driven grid wired to a `KeyAwareSmartRowCache`
- `BuckarooInfiniteWidget` — the full Buckaroo UI (status bar + grid + columns editor)
- `getKeySmartRowCache` — factory that wires a model's `infinite_request` / `infinite_resp` messages into a row cache

See `src/index.ts` for the full export surface.

## Development

```sh
pnpm install
pnpm run build           # tsc -b && vite build
pnpm test                # jest
pnpm run test:pw         # Playwright against Storybook
pnpm storybook           # interactive component dev
```

The package is part of the Buckaroo pnpm workspace at the repo root; see the [main README](https://github.com/paddymul/buckaroo) for the full build/release flow.

## License

[BSD-3-Clause](./LICENSE)
