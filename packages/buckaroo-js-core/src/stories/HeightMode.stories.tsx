import type { Meta, StoryObj } from "@storybook/react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { DFViewerConfig, NormalColumnConfig, ComponentConfig } from "../components/DFViewerParts/DFWhole";
import { ShadowDomWrapper } from "./StoryUtils";
import { DatasourceWrapper, createDatasourceWrapper, dictOfArraystoDFData, arange, NRandom } from "../components/DFViewerParts/DFViewerDataHelper";
import { useState, CSSProperties } from "react";

/**
 * Stories to test each HeightMode independently.
 *
 * Each story explicitly sets component_config.heightMode so the frontend
 * dispatches to the named strategy — no environment sniffing involved.
 */

const INDEX_COL_CONFIG: NormalColumnConfig = {
  col_name: "index",
  header_name: "index",
  displayer_args: { displayer: "string" },
};

const baseConfig: DFViewerConfig = {
  column_config: [
    { col_name: "a", header_name: "a", displayer_args: { displayer: "integer", min_digits: 1, max_digits: 5 } },
    { col_name: "b", header_name: "b", displayer_args: { displayer: "obj" } },
  ],
  pinned_rows: [],
  left_col_configs: [INDEX_COL_CONFIG],
};

const shortData = [
  { index: 0, a: 10, b: "foo" },
  { index: 1, a: 20, b: "bar" },
  { index: 2, a: 30, b: "baz" },
];

const MEDIUM = 300;
const mediumData = dictOfArraystoDFData({ a: NRandom(MEDIUM, 3, 50), b: arange(MEDIUM) });

// --- Wrapper components ---

/**
 * Fixed-size container for fraction and fixed mode stories.
 * Simulates a Jupyter/Colab output area with known dimensions.
 */
const FixedContainerViewer = ({
  data,
  component_config,
  containerHeight,
  containerWidth,
}: {
  data: any[];
  component_config: ComponentConfig;
  containerHeight: number;
  containerWidth: number;
}) => {
  const [activeCol, setActiveCol] = useState<[string, string]>(["a", "a"]);
  const data_wrapper: DatasourceWrapper = createDatasourceWrapper(data);
  const config: DFViewerConfig = { ...baseConfig, component_config };

  return (
    <ShadowDomWrapper>
      <div style={{ height: containerHeight, width: containerWidth }}>
        <DFViewerInfinite
          data_wrapper={data_wrapper}
          df_viewer_config={config}
          activeCol={activeCol}
          setActiveCol={setActiveCol}
        />
      </div>
    </ShadowDomWrapper>
  );
};

/**
 * Flex container for "fill" mode stories.
 * Simulates the MCP standalone page where the grid should fill all available space.
 * Uses display:flex + flex-direction:column so the grid's flex:1 style works.
 */
const FillContainerViewer = ({
  data,
  component_config,
  containerHeight,
  containerWidth,
}: {
  data: any[];
  component_config: ComponentConfig;
  containerHeight: number;
  containerWidth: number;
}) => {
  const [activeCol, setActiveCol] = useState<[string, string]>(["a", "a"]);
  const data_wrapper: DatasourceWrapper = createDatasourceWrapper(data);
  const config: DFViewerConfig = { ...baseConfig, component_config };

  const containerStyle: CSSProperties = {
    height: containerHeight,
    width: containerWidth,
    display: "flex",
    flexDirection: "column",
  };

  return (
    <ShadowDomWrapper>
      <div style={containerStyle}>
        <DFViewerInfinite
          data_wrapper={data_wrapper}
          df_viewer_config={config}
          activeCol={activeCol}
          setActiveCol={setActiveCol}
        />
      </div>
    </ShadowDomWrapper>
  );
};

// --- Meta ---

const meta = {
  title: "Buckaroo/DFViewer/HeightMode",
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;

// --- Stories ---

/** Fraction mode (Jupyter/Marimo) — 300 rows, grid takes ~half of 600px container */
export const FractionMode: StoryObj = {
  render: () => (
    <FixedContainerViewer
      data={mediumData}
      component_config={{ heightMode: "fraction", height_fraction: 2 }}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};

/** Fraction mode with short table — 3 rows should auto-size, not take half screen */
export const FractionModeShort: StoryObj = {
  render: () => (
    <FixedContainerViewer
      data={shortData}
      component_config={{ heightMode: "fraction", height_fraction: 2 }}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};

/** Fixed mode (Colab/VSCode) — 300 rows, grid is exactly 400px */
export const FixedMode: StoryObj = {
  render: () => (
    <FixedContainerViewer
      data={mediumData}
      component_config={{ heightMode: "fixed", dfvHeight: 400 }}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};

/** Fixed mode with short table — still 400px (fixed mode ignores short) */
export const FixedModeShort: StoryObj = {
  render: () => (
    <FixedContainerViewer
      data={shortData}
      component_config={{ heightMode: "fixed", dfvHeight: 400 }}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};

/** Fill mode (MCP standalone) — 300 rows, grid fills the full 600px container */
export const FillMode: StoryObj = {
  render: () => (
    <FillContainerViewer
      data={mediumData}
      component_config={{ heightMode: "fill" }}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};

/** Fill mode with short table — 3 rows should auto-size, NOT stretch to 600px */
export const FillModeShort: StoryObj = {
  render: () => (
    <FillContainerViewer
      data={shortData}
      component_config={{ heightMode: "fill" }}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};

/** No heightMode set — backward compat, should behave like fraction */
export const NoHeightMode: StoryObj = {
  render: () => (
    <FixedContainerViewer
      data={mediumData}
      component_config={{}}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};

/** No heightMode, short table — backward compat short mode */
export const NoHeightModeShort: StoryObj = {
  render: () => (
    <FixedContainerViewer
      data={shortData}
      component_config={{}}
      containerHeight={600}
      containerWidth={800}
    />
  ),
};
