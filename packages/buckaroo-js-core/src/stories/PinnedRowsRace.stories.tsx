import type { Meta, StoryObj } from "@storybook/react";
import { useMemo, useState } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { ShadowDomWrapper } from "./StoryUtils";
import {
  DatasourceWrapper,
  createDatasourceWrapper,
  dictOfArraystoDFData,
  arange,
} from "../components/DFViewerParts/DFViewerDataHelper";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";

type DFRow = Record<string, any>;

const idxCol: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "obj" },
};

const objCol = (name: string): NormalColumnConfig => ({
  col_name: name,
  header_name: name,
  displayer_args: { displayer: "obj" },
});

const pinnedCfg: DFViewerConfig = {
  column_config: [objCol("a"), objCol("b")],
  left_col_configs: [idxCol],
  pinned_rows: [
    { primary_key_val: "null_count", displayer_args: { displayer: "obj" } },
    { primary_key_val: "empty_count", displayer_args: { displayer: "obj" } },
  ],
};

const mainData = dictOfArraystoDFData({ a: arange(5), b: ["x", "y", "z", "w", "v"] });

const makeSummary = (variant: "loading" | "first" | "second"): DFRow[] => {
  if (variant === "loading") {
    return [
      { index: "null_count", a: "loading", b: "loading" },
      { index: "empty_count", a: "loading", b: "loading" },
    ];
  }
  if (variant === "first") {
    // Column-wise update: provide values for column 'a' only across both pinned rows
    return [
      { index: "null_count", a: 0, b: "loading" },
      { index: "empty_count", a: 2, b: "loading" },
    ];
  }
  return [
    // Finalize column 'b' values; column 'a' already set in the previous step
    { index: "null_count", a: 0, b: 1 },
    { index: "empty_count", a: 2, b: 3 },
  ];
};

const PinnedRowsRaceInner = () => {
  const [summary, setSummary] = useState<DFRow[]>(makeSummary("loading"));
  const [useFiveRows, setUseFiveRows] = useState(false);
  const data_wrapper: DatasourceWrapper = useMemo(() => {
    // Use the infinite datasource path. Start with 0 rows, then swap to 5 rows.
    const base = useFiveRows ? mainData : dictOfArraystoDFData({ a: [], b: [] });
    // No artificial delay; we control timing via setTimeout below.
    return createDatasourceWrapper(base, 0);
  }, [useFiveRows]);

  const start = () => {
    // 1) Initial pinned rows: "loading" already set via initial state
    // 2) After 3s, load 5 rows for table body (swap datasource)
    setTimeout(() => setUseFiveRows(true), 3000);
    // 3) After another 3s, update first pinned metric
    setTimeout(() => setSummary(makeSummary("first")), 6000);
    // 4) After another 4s, update second pinned metric
    setTimeout(() => setSummary(makeSummary("second")), 10000);
  };

  return (
    <ShadowDomWrapper>
      <div style={{ width: 720 }}>
        <p style={{ marginBottom: 8 }}>
          Scenario: Instantiate DFViewerInfinite with pinned rows configured. We first load initial
          pinned rows with the text "loading". After 3 seconds, the infinite row datasource returns 5
          rows for the table body. After another 3 seconds, update only column "a" across the pinned
          rows (column-wise update). After a further 4 seconds, update column "b" across pinned rows.
          Expected: pinned rows remain visible and reflect column-wise updates progressively. Actual:
          depending on timing, the datasource render can clear pinned rows
          and reflect updates. Actual: depending on timing, the datasource render can clear pinned rows
          after they were applied, unless we re-apply them after the grid finishes binding (for example,
          in onFirstDataRendered) and on subsequent updates.
        </p>
        <div style={{ marginBottom: 8 }}>
          <button onClick={start}>Start (apply stats, then recreate datasource)</button>
        </div>
        <div style={{ height: 420 }}>
          <DFViewerInfinite
            data_wrapper={data_wrapper}
            df_viewer_config={pinnedCfg}
            summary_stats_data={summary}
            activeCol={["a", "a"]}
            setActiveCol={() => {}}
            outside_df_params={{}}
          />
        </div>
      </div>
    </ShadowDomWrapper>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/PinnedRowsRace",
  component: PinnedRowsRaceInner,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof PinnedRowsRaceInner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {},
};
//FIXME: add a playwright test for this.  tighten up the timing to 1 second delays.  add toggle in storybook UI to change to longer timeouts



