/**
 * The Jupyter widget (packages/js/widget.tsx) decodes ``df_data_dict`` before
 * it renders. Decoding is async, so a slow decode of an older dict can finish
 * after a newer one and must not be rendered over it (#1046).
 *
 * Decodes are held open here so the test chooses the order they finish in.
 */
export {};

const mockPending: Array<{ raw: any; resolve: (decoded: any) => void }> = [];
const mockDecode = (raw: any) =>
  new Promise<any>((resolve) => mockPending.push({ raw, resolve }));
const mockRoot = { render: jest.fn(), unmount: jest.fn() };

// Virtual, so the mock applies to the imports in packages/js/widget.tsx too.
jest.mock("react-dom/client", () => ({ createRoot: () => mockRoot }), { virtual: true });
jest.mock("../components/DFViewerParts/resolveDFData", () => ({
  decodeDFDataDict: (raw: any) => mockDecode(raw),
}));
jest.mock(
  "buckaroo-js-core",
  () => ({
    __esModule: true,
    default: {
      decodeDFDataDict: (raw: any) => mockDecode(raw),
      makeLatestDictDecoder: jest.requireActual("./latestDictDecoder").makeLatestDictDecoder,
    },
  }),
  { virtual: true },
);

// packages/js is built by esbuild and is not strict-clean, so this project's
// tsc must not follow an import into it. Load it untyped, after the mocks.
const { createPredecodingRender } = require("../../../js/widget");

function makeModel(initial: any) {
  const handlers: Record<string, Array<() => void>> = {};
  let dict = initial;
  return {
    get: (key: string) => (key === "df_data_dict" ? dict : undefined),
    on: (event: string, fn: () => void) => {
      (handlers[event] = handlers[event] || []).push(fn);
    },
    off: (event: string, fn: () => void) => {
      handlers[event] = (handlers[event] || []).filter((h) => h !== fn);
    },
    setDict(next: any) {
      dict = next;
      (handlers["change:df_data_dict"] || []).forEach((fn) => fn());
    },
  };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const renderedDicts = () =>
  mockRoot.render.mock.calls.map(([element]) => element.props.children.props.resolvedDFDataDict);

beforeEach(() => {
  mockPending.length = 0;
  mockRoot.render.mockClear();
  mockRoot.unmount.mockClear();
});

test("a slow decode of an older df_data_dict does not overwrite a newer one", async () => {
  const older = { all_stats: { raw: "older" } };
  const newer = { all_stats: { raw: "newer" } };
  const model = makeModel(older);
  const render = createPredecodingRender(() => null);
  render({ el: document.createElement("div"), model, experimental: {} });
  model.setDict(newer);
  expect(mockPending.map((p) => p.raw)).toEqual([older, newer]);

  const decodedNewer = { all_stats: [{ index: "newer" }] };
  const decodedOlder = { all_stats: [{ index: "older" }] };
  mockPending[1].resolve(decodedNewer);
  await flush();
  mockPending[0].resolve(decodedOlder);
  await flush();

  const rendered = renderedDicts();
  expect(rendered[rendered.length - 1]).toBe(decodedNewer);
});
