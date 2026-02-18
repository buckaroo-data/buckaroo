import type { Meta, StoryObj } from "@storybook/react";
import { useMemo } from "react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { DFViewerConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";
import { DatasourceWrapper } from "../components/DFViewerParts/DFViewerDataHelper";
import { getDs } from "../components/DFViewerParts/gridUtils";
import {
  KeyAwareSmartRowCache,
  PayloadArgs,
  PayloadResponse,
} from "../components/DFViewerParts/SmartRowCache";

/**
 * Generates deterministic test data: 200 rows with index, a (integer), b (string).
 */
const TOTAL_ROWS = 200;
const allData = Array.from({ length: TOTAL_ROWS }, (_, i) => ({
  index: i,
  a: i * 10,
  b: `row_${i}`,
}));

/**
 * A component that wires up KeyAwareSmartRowCache + getDs(),
 * exercising the real infinite scroll cache path with a small dataset.
 * This reproduces the blank-rows-on-scroll bug.
 */
const SmallDFScrollComponent = () => {
  const src = useMemo(() => {
    const cache = new KeyAwareSmartRowCache((pa: PayloadArgs) => {
      // Simulate server: slice from allData, cap at TOTAL_ROWS
      const dataEnd = Math.min(pa.end, TOTAL_ROWS);
      if (dataEnd <= pa.start) return;
      const resp: PayloadResponse = {
        key: pa,
        data: allData.slice(pa.start, dataEnd),
        length: TOTAL_ROWS,
      };
      // Async response like a real server
      setTimeout(() => cache.addPayloadResponse(resp), 10);
    });
    return cache;
  }, []);

  const dataWrapper: DatasourceWrapper = useMemo(() => {
    const ds = getDs(src);
    return {
      datasource: ds,
      data_type: "DataSource" as const,
      length: TOTAL_ROWS,
    };
  }, [src]);

  return (
    <div style={{ height: 500, width: 800 }}>
      <DFViewerInfinite
        data_wrapper={dataWrapper}
        df_viewer_config={dfViewerConfig}
        setActiveCol={() => {}}
      />
    </div>
  );
};

const INDEX_COL_CONFIG: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "string" },
};

const dfViewerConfig: DFViewerConfig = {
  column_config: [
    {
      col_name: "a",
      header_name: "a",
      displayer_args: { displayer: "integer", min_digits: 1, max_digits: 5 },
    },
    {
      col_name: "b",
      header_name: "b",
      displayer_args: { displayer: "obj" },
    },
  ],
  pinned_rows: [],
  left_col_configs: [INDEX_COL_CONFIG],
};

const meta = {
  title: "Buckaroo/DFViewer/SmallDFScroll",
  component: SmallDFScrollComponent,
  parameters: { layout: "centered" },
} satisfies Meta<typeof SmallDFScrollComponent>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = {};
