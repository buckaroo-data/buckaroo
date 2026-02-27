/**
 * Stories to reproduce styling / column-width issues:
 *   #587 – pinned-row index alignment
 *   #595 / #596 / #599 / #600 – column width contention (few vs many, short vs long headers/data)
 *   #597 – compact_number displayer for large values
 *   #602 – compact_number precision loss on clustered billion-scale values
 *
 * Full 2×2×2 combinatorial matrix for width stories, plus large-number and pinned-row scenarios.
 */
import type { Meta, StoryObj } from "@storybook/react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { ShadowDomWrapper } from "./StoryUtils";
import {
  DFViewerConfig,
  NormalColumnConfig,
  PinnedRowConfig,
} from "../components/DFViewerParts/DFWhole";

type DFRow = Record<string, any>;

// ── Column header name pools ────────────────────────────────────────────────

const SHORT_HEADER_NAMES = [
  "a","b","c","d","e","f","g","h","i","j","k","l","m",
  "n","o","p","q","r","s","t","u","v","w","x","y",
];

const LONG_HEADER_NAMES = [
  "revenue_total","customer_count","margin_pct_adj","transaction_vol",
  "active_users_n","retention_rate","avg_order_val","monthly_recur_r",
  "churn_pct_adj","lifetime_value","gross_margin_rt","net_promoter_sc",
  "conv_rate_pct","acq_cost_avg","rev_per_user_q","visits_monthly",
  "bounce_rate_pc","avg_session_s","page_views_tot","email_open_rt",
  "click_thru_pct","refund_rate_pc","support_tkts","upsell_rev_q",
  "referral_cnt",
];

const INDEX_COL: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "obj" },
};

// ── Data generators ─────────────────────────────────────────────────────────

const ROW_COUNT = 20;

type DataStyle = "short" | "long" | "large" | "clustered";
type HeaderStyle = "short" | "long";

function makeShortVal(row: number, col: number): number {
  return ((row * 7 + col * 3 + 1) % 99) + 1; // 1–99
}

function makeLongVal(row: number, col: number): number {
  return 100_000 + ((row * 1_234_567 + col * 234_567) % 9_900_000); // 100k–9.9M
}

function makeLargeVal(row: number, col: number): number {
  // 3M – 5.7B spread
  return 3_000_000 + ((row * 987_654_321 + col * 123_456_789) % 5_697_000_000);
}

function makeClusteredVal(row: number, col: number): number {
  // 5.60B – 5.68B (tight cluster to expose compact_number precision loss)
  return 5_600_000_000 + ((row * 12_345 + col * 5_678) % 80_000_000);
}

function genData(count: number, dataStyle: DataStyle): DFRow[] {
  const valFn =
    dataStyle === "short" ? makeShortVal :
    dataStyle === "long"  ? makeLongVal  :
    dataStyle === "large" ? makeLargeVal :
                            makeClusteredVal;

  return Array.from({ length: ROW_COUNT }, (_, row) => {
    const r: DFRow = { index: row };
    for (let col = 0; col < count; col++) {
      r[`col_${col}`] = valFn(row, col);
    }
    return r;
  });
}

function genSummary(count: number, dataStyle: DataStyle): DFRow[] {
  const colKeys = Array.from({ length: count }, (_, i) => `col_${i}`);
  const isFloat = dataStyle === "large" || dataStyle === "clustered";
  const dtype = isFloat ? "float64" : "int64";

  const row = (key: string, valFn: (i: number) => number | string): DFRow => {
    const r: DFRow = { index: key };
    colKeys.forEach((k, i) => { r[k] = valFn(i); });
    return r;
  };

  if (dataStyle === "short") {
    return [
      row("dtype",         () => dtype),
      row("non_null_count",() => ROW_COUNT),
      row("mean",          (i) => 40 + i * 3),
      row("std",           (i) => 20 + i),
      row("min",           (i) => 1 + i),
      row("max",           (i) => 90 + i),
    ];
  } else if (dataStyle === "long") {
    return [
      row("dtype",         () => dtype),
      row("non_null_count",() => ROW_COUNT),
      row("mean",          (i) => 5_000_000 + i * 100_000),
      row("std",           (i) => 2_000_000 + i * 50_000),
      row("min",           (i) => 100_000  + i * 10_000),
      row("max",           (i) => 9_800_000 + i * 10_000),
    ];
  } else if (dataStyle === "large") {
    return [
      row("dtype",         () => dtype),
      row("non_null_count",() => ROW_COUNT),
      row("mean",          (i) => 2_000_000_000 + i * 100_000_000),
      row("std",           ()  => 1_000_000_000),
      row("min",           (i) => 3_000_000 + i * 1_000_000),
      row("max",           ()  => 5_700_000_000),
    ];
  } else {
    return [
      row("dtype",         () => dtype),
      row("non_null_count",() => ROW_COUNT),
      row("mean",          () => 5_640_000_000),
      row("std",           () => 20_000_000),
      row("min",           () => 5_600_000_000),
      row("max",           () => 5_680_000_000),
    ];
  }
}

// ── Config builders ─────────────────────────────────────────────────────────

function genConfig(
  count: number,
  headerStyle: HeaderStyle,
  dataStyle: DataStyle,
  withPinned = false,
): DFViewerConfig {
  const headers =
    headerStyle === "short" ? SHORT_HEADER_NAMES : LONG_HEADER_NAMES;

  const displayer_args = (): NormalColumnConfig["displayer_args"] => {
    if (dataStyle === "large" || dataStyle === "clustered") {
      return { displayer: "float", min_fraction_digits: 2, max_fraction_digits: 2 };
    }
    return {
      displayer: "integer",
      min_digits: 1,
      max_digits: dataStyle === "short" ? 2 : 7,
    };
  };

  const column_config: NormalColumnConfig[] = Array.from({ length: count }, (_, i) => ({
    col_name: `col_${i}`,
    header_name: headers[i % headers.length],
    displayer_args: displayer_args(),
  }));

  const pinned_rows: PinnedRowConfig[] = withPinned
    ? [
        { primary_key_val: "dtype",         displayer_args: { displayer: "obj" } },
        { primary_key_val: "non_null_count", displayer_args: { displayer: "inherit" } },
        { primary_key_val: "mean",           displayer_args: { displayer: "inherit" } },
        { primary_key_val: "std",            displayer_args: { displayer: "inherit" } },
        { primary_key_val: "min",            displayer_args: { displayer: "inherit" } },
        { primary_key_val: "max",            displayer_args: { displayer: "inherit" } },
      ]
    : [];

  return { column_config, left_col_configs: [INDEX_COL], pinned_rows };
}

// ── Story factory ───────────────────────────────────────────────────────────

function makeStoryComponent(
  config: DFViewerConfig,
  data: DFRow[],
  summary: DFRow[] = [],
  width = 800,
) {
  const data_wrapper = { data_type: "Raw" as const, data, length: data.length };
  return function StoryInner() {
    return (
      <ShadowDomWrapper>
        <div style={{ height: 500, width }}>
          <DFViewerInfinite
            data_wrapper={data_wrapper}
            df_viewer_config={config}
            summary_stats_data={summary}
            activeCol={["col_0", "col_0"]}
            setActiveCol={() => {}}
            outside_df_params={{}}
          />
        </div>
      </ShadowDomWrapper>
    );
  };
}

// ── Meta ────────────────────────────────────────────────────────────────────

// Placeholder component; all stories use render() below
const _Placeholder = () => null;

const meta = {
  title: "Buckaroo/DFViewer/StylingIssues",
  component: _Placeholder,
  parameters: { layout: "centered" },
} satisfies Meta<typeof _Placeholder>;

export default meta;
type Story = StoryObj<typeof meta>;

// ── Section A: Width / contention (#595, #596, #599, #600) ─────────────────
// Full 2×2×2 = 8 combinations of: col count × header length × data length

const FewShortShortInner = makeStoryComponent(
  genConfig(5, "short", "short"),
  genData(5, "short"),
);
/** Baseline – 5 cols, 1-char headers, 1-2 digit values. Should look fine. (#599) */
export const FewCols_ShortHdr_ShortData: Story = {
  render: () => <FewShortShortInner />,
};

const FewShortLongInner = makeStoryComponent(
  genConfig(5, "short", "long"),
  genData(5, "long"),
);
/** 5 cols, 1-char headers, 6-7 digit values. Data drives width, no contention. */
export const FewCols_ShortHdr_LongData: Story = {
  render: () => <FewShortLongInner />,
};

const FewLongShortInner = makeStoryComponent(
  genConfig(5, "long", "short"),
  genData(5, "short"),
);
/** 5 cols, 12-18 char headers, 1-2 digit values. Header wider than data. */
export const FewCols_LongHdr_ShortData: Story = {
  render: () => <FewLongShortInner />,
};

const FewLongLongInner = makeStoryComponent(
  genConfig(5, "long", "long"),
  genData(5, "long"),
);
/** 5 cols, long headers, long data. Both are wide; no contention at 5 cols. */
export const FewCols_LongHdr_LongData: Story = {
  render: () => <FewLongLongInner />,
};

const ManyShortShortInner = makeStoryComponent(
  genConfig(25, "short", "short"),
  genData(25, "short"),
);
/** 25 cols, 1-char headers, 1-2 digit values. Primary bug case (#595/#599). */
export const ManyCols_ShortHdr_ShortData: Story = {
  render: () => <ManyShortShortInner />,
};

const ManyShortLongInner = makeStoryComponent(
  genConfig(25, "short", "long"),
  genData(25, "long"),
);
/** 25 cols, 1-char headers, 6-7 digit values. Data wants space (#596). */
export const ManyCols_ShortHdr_LongData: Story = {
  render: () => <ManyShortLongInner />,
};

const ManyLongShortInner = makeStoryComponent(
  genConfig(25, "long", "short"),
  genData(25, "short"),
);
/** 25 cols, 12-18 char headers, 1-2 digit values. Headers want space (#596). */
export const ManyCols_LongHdr_ShortData: Story = {
  render: () => <ManyLongShortInner />,
};

const ManyLongLongInner = makeStoryComponent(
  genConfig(25, "long", "long"),
  genData(25, "long"),
);
/** 25 cols, long headers, long data. Worst-case contention (#596). */
export const ManyCols_LongHdr_LongData: Story = {
  render: () => <ManyLongLongInner />,
};

// ── Section B: Large numbers / compact (#597, #602) ─────────────────────────

const largeFloatConfig: DFViewerConfig = {
  column_config: Array.from({ length: 5 }, (_, i) => ({
    col_name: `col_${i}`,
    header_name: SHORT_HEADER_NAMES[i],
    displayer_args: { displayer: "float" as const, min_fraction_digits: 2, max_fraction_digits: 2 },
  })),
  left_col_configs: [INDEX_COL],
  pinned_rows: [],
};
const largeData = genData(5, "large");

const LargeNumbersFloatInner = makeStoryComponent(largeFloatConfig, largeData);
/** 5 cols, values 3M–5.7B, float displayer. Shows why compact is needed (#597). */
export const LargeNumbers_Float: Story = {
  render: () => <LargeNumbersFloatInner />,
};

const largeCompactConfig: DFViewerConfig = {
  column_config: Array.from({ length: 5 }, (_, i) => ({
    col_name: `col_${i}`,
    header_name: SHORT_HEADER_NAMES[i],
    displayer_args: { displayer: "compact_number" as const },
  })),
  left_col_configs: [INDEX_COL],
  pinned_rows: [],
};

const LargeNumbersCompactInner = makeStoryComponent(largeCompactConfig, largeData);
/** Same data as LargeNumbers_Float but using compact_number displayer (#597 fix). */
export const LargeNumbers_Compact: Story = {
  render: () => <LargeNumbersCompactInner />,
};

const clusteredData = genData(5, "clustered");

const clusteredFloatConfig: DFViewerConfig = {
  column_config: Array.from({ length: 5 }, (_, i) => ({
    col_name: `col_${i}`,
    header_name: SHORT_HEADER_NAMES[i],
    displayer_args: { displayer: "float" as const, min_fraction_digits: 2, max_fraction_digits: 2 },
  })),
  left_col_configs: [INDEX_COL],
  pinned_rows: [],
};

const ClusteredBillionsFloatInner = makeStoryComponent(clusteredFloatConfig, clusteredData);
/** 5 cols, values tightly clustered 5.60B–5.68B, float displayer (#602 baseline). */
export const ClusteredBillions_Float: Story = {
  render: () => <ClusteredBillionsFloatInner />,
};

const clusteredCompactConfig: DFViewerConfig = {
  column_config: Array.from({ length: 5 }, (_, i) => ({
    col_name: `col_${i}`,
    header_name: SHORT_HEADER_NAMES[i],
    displayer_args: { displayer: "compact_number" as const },
  })),
  left_col_configs: [INDEX_COL],
  pinned_rows: [],
};

const ClusteredBillionsCompactInner = makeStoryComponent(clusteredCompactConfig, clusteredData);
/** Same clustered data with compact_number – exposes precision loss (#602). */
export const ClusteredBillions_Compact: Story = {
  render: () => <ClusteredBillionsCompactInner />,
};

// ── Section C: Pinned row / index (#587) ────────────────────────────────────

const pinnedFewCfg = genConfig(10, "long", "short", true);
const pinnedFewData = genData(10, "short");
const pinnedFewSummary = genSummary(10, "short");

const PinnedIndexFewInner = makeStoryComponent(pinnedFewCfg, pinnedFewData, pinnedFewSummary, 400);
/** 10 long-header cols + pinned summary stats + left index. Tests #587 alignment. */
export const PinnedIndex_FewCols: Story = {
  render: () => <PinnedIndexFewInner />,
};

const pinnedManyCfg = genConfig(20, "long", "short", true);
const pinnedManyData = genData(20, "short");
const pinnedManySummary = genSummary(20, "short");

const PinnedIndexManyInner = makeStoryComponent(pinnedManyCfg, pinnedManyData, pinnedManySummary, 400);
/** 20 long-header cols + pinned summary stats. #587 alignment under width contention. */
export const PinnedIndex_ManyCols: Story = {
  render: () => <PinnedIndexManyInner />,
};

// ── Section D: Mixed scenarios ───────────────────────────────────────────────

const mixedManyNarrowCfg = genConfig(20, "long", "short", true);
const mixedManyNarrowData = genData(20, "short");
const mixedManyNarrowSummary = genSummary(20, "short");

const MixedManyNarrowInner = makeStoryComponent(
  mixedManyNarrowCfg, mixedManyNarrowData, mixedManyNarrowSummary, 400,
);
/** 20 narrow cols + pinned rows. Cross-issue: #595 + #587 + #599. */
export const Mixed_ManyNarrow_WithPinned: Story = {
  render: () => <MixedManyNarrowInner />,
};

const mixedFewWideCfg = genConfig(5, "long", "long", true);
const mixedFewWideData = genData(5, "long");
const mixedFewWideSummary = genSummary(5, "long");

const MixedFewWideInner = makeStoryComponent(
  mixedFewWideCfg, mixedFewWideData, mixedFewWideSummary, 400,
);
/** 5 wide cols + pinned rows. #587 baseline (should look fine). */
export const Mixed_FewWide_WithPinned: Story = {
  render: () => <MixedFewWideInner />,
};
