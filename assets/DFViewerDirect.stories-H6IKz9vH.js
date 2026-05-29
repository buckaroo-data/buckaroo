import{j as r}from"./jsx-runtime-DiklIkkE.js";/* empty css                */import{D as t}from"./DFViewerInfinite--8V4ilcC.js";import"./index-DRjF_FHU.js";import"./gridUtils-CtpEWCZ8.js";import"./main.esm-KSBVO7T_.js";import"./_baseEach-C9E3e27i.js";import"./isArray-Dxzbedgu.js";import"./HistogramCell-qbNrk3qL.js";import"./index-DIvcuAjW.js";import"./ChartCell-DjlNlKxO.js";import"./tiny-invariant-CopsF_GD.js";import"./isString-SHB7N511.js";import"./index.esm-Br-1or4R.js";const S={title:"Buckaroo/Direct/DFViewer",component:t,parameters:{layout:"centered",docs:{description:{component:'Direct `<DFViewer>` consumer pattern — no wrapper component, no hooks\nin a `render` function. `meta.component` is `DFViewer` itself and each\nstory passes prop values via `args:`, so Storybook\'s "Show code" view\ndisplays the actual JSX an `npm install buckaroo-js-core` consumer\nwould paste into their React app (literal `df_data` array, literal\n`df_viewer_config` object), not a `render()` arrow function.\n\nA `decorators` entry wraps the rendered output in a sized container —\ndecorators are not part of the "Show code" output, so they keep the\nstory functional without obscuring the consumer-facing API.'}}},decorators:[a=>r.jsx("div",{style:{width:720,height:400},children:r.jsx(a,{})})],tags:["autodocs"]},s=[{index:0,region:"North",revenue:12500,units:320},{index:1,region:"South",revenue:9800,units:240},{index:2,region:"East",revenue:15700,units:410},{index:3,region:"West",revenue:11200,units:290},{index:4,region:"Central",revenue:7300,units:175}],d={column_config:[{col_name:"region",header_name:"Region",displayer_args:{displayer:"string"}},{col_name:"revenue",header_name:"Revenue ($)",displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},color_map_config:{color_rule:"color_map",val_column:"revenue",map_name:"BLUE_TO_YELLOW"}},{col_name:"units",header_name:"Units",displayer_args:{displayer:"integer",min_digits:1,max_digits:4}}],pinned_rows:[],left_col_configs:[{col_name:"index",header_name:"#",displayer_args:{displayer:"string"}}]},c=`<DFViewer
  df_data={[
    { index: 0, region: "North",   revenue: 12500, units: 320 },
    { index: 1, region: "South",   revenue:  9800, units: 240 },
    { index: 2, region: "East",    revenue: 15700, units: 410 },
    { index: 3, region: "West",    revenue: 11200, units: 290 },
    { index: 4, region: "Central", revenue:  7300, units: 175 },
  ]}
  df_viewer_config={{
    column_config: [
      { col_name: "region",  header_name: "Region",      displayer_args: { displayer: "string" } },
      { col_name: "revenue", header_name: "Revenue ($)", displayer_args: { displayer: "float", min_fraction_digits: 0, max_fraction_digits: 0 }, color_map_config: { color_rule: "color_map", val_column: "revenue", map_name: "BLUE_TO_YELLOW" } },
      { col_name: "units",   header_name: "Units",       displayer_args: { displayer: "integer" } },
    ],
    pinned_rows: [],
    left_col_configs: [
      { col_name: "index", header_name: "#", displayer_args: { displayer: "string" } },
    ],
  }}
/>`,e={args:{df_data:s,df_viewer_config:d},parameters:{docs:{source:{code:c}}}};var n,o,i;e.parameters={...e.parameters,docs:{...(n=e.parameters)==null?void 0:n.docs,source:{originalSource:`{
  args: {
    df_data,
    df_viewer_config
  },
  parameters: {
    docs: {
      source: {
        code: PRIMARY_SOURCE
      }
    }
  }
}`,...(i=(o=e.parameters)==null?void 0:o.docs)==null?void 0:i.source}}};const D=["Primary"];export{e as Primary,D as __namedExportsOrder,S as default};
