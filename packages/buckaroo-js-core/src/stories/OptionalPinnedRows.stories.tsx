/**
 * Story to verify the `?key` optional-pinned-row prefix added in PR #777.
 *
 * `PinnedRowConfig.primary_key_val` now supports a leading `?` that marks
 * the row as optional: if the unprefixed key isn't found in the summary
 * stats data, the row is omitted entirely (instead of rendering with
 * undefined values, which is what a required row does).
 *
 * Use case: ship one default config containing `?cleaned_*` and
 * `?filtered_*` entries; only the rows for active scopes actually render.
 *
 * Interactive: the toggle flips between three states so you can see
 * pinned rows appear/disappear in real time without re-mounting the grid:
 *   - "raw"      → summary stats has only bare keys (mean, median, ...)
 *                  Expected: `?filtered_*` and `?cleaned_*` rows omitted.
 *   - "filter"   → summary stats also has `filtered_*` keys
 *                  Expected: `?filtered_*` rows appear, `?cleaned_*` still omitted.
 *   - "filter+clean" → summary stats also has both `filtered_*` and `cleaned_*`
 *                  Expected: all optional rows appear.
 *
 * Also includes a "required-missing" row (no `?` prefix, key absent) that
 * stays as an undefined row — proving backward-compat.
 */
import type { Meta, StoryObj } from "@storybook/react";
import { useMemo, useState } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { ShadowDomWrapper, SelectBox } from "./StoryUtils";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";

type DFRow = Record<string, any>;

const idxCol: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "obj" },
};

const intCol: NormalColumnConfig = {
  col_name: "station_id",
  header_name: "station_id",
  displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 },
};

const floatCol: NormalColumnConfig = {
  col_name: "temperature",
  header_name: "temperature",
  displayer_args: { displayer: "float", min_fraction_digits: 3, max_fraction_digits: 3 },
};

/**
 * Pinned config exercising all three flavors:
 *   - required, present       → renders normally
 *   - required, absent        → renders as undefined row (backward-compat)
 *   - optional `?`, present   → renders normally
 *   - optional `?`, absent    → row omitted entirely
 */
const viewerConfig: DFViewerConfig = {
  column_config: [intCol, floatCol],
  left_col_configs: [idxCol],
  pinned_rows: [
    { primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
    { primary_key_val: "mean", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "median", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "min", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "max", displayer_args: { displayer: "inherit" } },
    // required but absent: stays as an `undefined` row (backward-compat)
    { primary_key_val: "always_missing_required", displayer_args: { displayer: "inherit" } },
    // optional, scope-conditional:
    { primary_key_val: "?filtered_mean", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "?filtered_median", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "?cleaned_min", displayer_args: { displayer: "inherit" } },
    { primary_key_val: "?cleaned_max", displayer_args: { displayer: "inherit" } },
  ],
};

const mainData: DFRow[] = [
  { index: 0, station_id: 519, temperature: 22.5 },
  { index: 1, station_id: 497, temperature: 18.3 },
  { index: 2, station_id: 402, temperature: 25.1 },
  { index: 3, station_id: 435, temperature: 19.8 },
  { index: 4, station_id: 293, temperature: 21.0 },
];

const rawStats: DFRow[] = [
  { index: "dtype", station_id: "int64", temperature: "float64" },
  { index: "mean", station_id: 429.2, temperature: 21.34 },
  { index: "median", station_id: 435, temperature: 21.0 },
  { index: "min", station_id: 293, temperature: 18.3 },
  { index: "max", station_id: 519, temperature: 25.1 },
];

const filteredOverlay: DFRow[] = [
  { index: "filtered_mean", station_id: 466.0, temperature: 22.7 },
  { index: "filtered_median", station_id: 466.0, temperature: 22.7 },
];

const cleanedOverlay: DFRow[] = [
  { index: "cleaned_min", station_id: 293, temperature: 18.3 },
  { index: "cleaned_max", station_id: 519, temperature: 25.1 },
];

type Scope = "raw" | "filter" | "filter+clean";
const ALL_SCOPES: Scope[] = ["raw", "filter", "filter+clean"];

const buildStats = (scope: Scope): DFRow[] => {
  let out = [...rawStats];
  if (scope === "filter" || scope === "filter+clean") out = out.concat(filteredOverlay);
  if (scope === "filter+clean") out = out.concat(cleanedOverlay);
  return out;
};

const OptionalPinnedRowsInner = () => {
  const [scope, setScope] = useState<Scope>("raw");
  const data_wrapper = useMemo(
    () => ({
      data_type: "Raw" as const,
      data: mainData,
      length: mainData.length,
    }),
    [],
  );
  const summary_stats_data = useMemo(() => buildStats(scope), [scope]);

  return (
    <ShadowDomWrapper>
      <div style={{ width: 720 }}>
        <div style={{ padding: "8px 12px", background: "#f4f4f4", marginBottom: 8 }}>
          <SelectBox<Scope>
            label="Active scope"
            options={ALL_SCOPES}
            value={scope}
            onChange={setScope}
          />
          <span style={{ marginLeft: 12, fontFamily: "monospace", fontSize: 12 }}>
            { scope === "raw"
                ? "Only bare keys → ?filtered_* and ?cleaned_* rows OMITTED"
                : scope === "filter"
                ? "filter active → ?filtered_* rows VISIBLE, ?cleaned_* OMITTED"
                : "filter + clean active → all optional rows VISIBLE" }
          </span>
        </div>
        <div style={{ height: 500 }}>
          <DFViewerInfinite
            data_wrapper={data_wrapper}
            df_viewer_config={viewerConfig}
            summary_stats_data={summary_stats_data}
            activeCol={["station_id", "station_id"]}
            setActiveCol={() => {}}
            outside_df_params={{}}
          />
        </div>
      </div>
    </ShadowDomWrapper>
  );
};

const meta = {
  title: "Buckaroo/DFViewer/OptionalPinnedRows",
  component: OptionalPinnedRowsInner,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof OptionalPinnedRowsInner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {},
};
