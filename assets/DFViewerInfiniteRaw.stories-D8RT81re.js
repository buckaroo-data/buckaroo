import{j as a}from"./jsx-runtime-DiklIkkE.js";import{a as g}from"./gridUtils-D90EcRKp.js";import{r as f}from"./DFViewerDataHelper-BfQga_7q.js";import"./index-DRjF_FHU.js";import"./HistogramCell-Bzivjlh2.js";import"./index-DIvcuAjW.js";import"./ChartCell-BfPIzAg-.js";import"./isArray-Dxzbedgu.js";import"./tiny-invariant-CopsF_GD.js";import"./_baseEach-B-y44WsN.js";import"./isString-CNnovG4X.js";import"./main.esm-BoVfKTQ4.js";const u=({data_wrapper:o,df_viewer_config:t,summary_stats_data:s,activeCol:m,setActiveCol:_,outside_df_params:d,error_info:c})=>{const l=_||(p=>{console.log("defaultSetColumnFunc",p)});return a.jsx("div",{style:{height:500,width:800},children:a.jsx(g,{data_wrapper:o,df_viewer_config:t,summary_stats_data:s,activeCol:m,setActiveCol:l,outside_df_params:d,error_info:c})})},N={title:"Buckaroo/DFViewer/DFViewerInfiniteRaw",component:u,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},y={col_name:"index",header_name:"index",displayer_args:{displayer:"string"}},w=[y],e={args:{data_wrapper:f,df_viewer_config:{column_config:[{col_name:"a",header_name:"a1",displayer_args:{displayer:"float",min_fraction_digits:2,max_fraction_digits:8}},{col_name:"a",header_name:"a2",displayer_args:{displayer:"integer",min_digits:2,max_digits:3}},{col_name:"b",header_name:"b",displayer_args:{displayer:"obj"}}],pinned_rows:[],left_col_configs:w}}};var n,r,i;e.parameters={...e.parameters,docs:{...(n=e.parameters)==null?void 0:n.docs,source:{originalSource:`{
  args: {
    data_wrapper: rd,
    df_viewer_config: {
      column_config: [{
        col_name: 'a',
        header_name: 'a1',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 2,
          max_fraction_digits: 8
        }
        //tooltip_config: { tooltip_type: 'summary_series' },
      }, {
        col_name: 'a',
        header_name: 'a2',
        displayer_args: {
          displayer: 'integer',
          min_digits: 2,
          max_digits: 3
        }
      }, {
        col_name: 'b',
        header_name: 'b',
        displayer_args: {
          displayer: 'obj'
        }
      }],
      pinned_rows: [],
      left_col_configs
    }
  }
}`,...(i=(r=e.parameters)==null?void 0:r.docs)==null?void 0:i.source}}};const P=["Primary"];export{e as Primary,P as __namedExportsOrder,N as default};
