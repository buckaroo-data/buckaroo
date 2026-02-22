import{j as a}from"./jsx-runtime-DiklIkkE.js";import{a as g}from"./gridUtils-sSkkIXDy.js";import{r as f}from"./DFViewerDataHelper-l27HaZum.js";import"./index-DRjF_FHU.js";import"./lodash-CGIzQN7T.js";import"./HistogramCell-DJbyo4_Z.js";import"./index-Bx0Ph3cE.js";import"./ChartCell-ClfxlV_N.js";import"./tiny-invariant-CopsF_GD.js";import"./main.esm-B8BDqAWP.js";const u=({data_wrapper:o,df_viewer_config:t,summary_stats_data:s,activeCol:_,setActiveCol:d,outside_df_params:m,error_info:c})=>{const l=d||(p=>{console.log("defaultSetColumnFunc",p)});return a.jsx("div",{style:{height:500,width:800},children:a.jsx(g,{data_wrapper:o,df_viewer_config:t,summary_stats_data:s,activeCol:_,setActiveCol:l,outside_df_params:m,error_info:c})})},E={title:"Buckaroo/DFViewer/DFViewerInfiniteRaw",component:u,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},y={col_name:"index",header_name:"index",displayer_args:{displayer:"string"}},w=[y],e={args:{data_wrapper:f,df_viewer_config:{column_config:[{col_name:"a",header_name:"a1",displayer_args:{displayer:"float",min_fraction_digits:2,max_fraction_digits:8}},{col_name:"a",header_name:"a2",displayer_args:{displayer:"integer",min_digits:2,max_digits:3}},{col_name:"b",header_name:"b",displayer_args:{displayer:"obj"}}],pinned_rows:[],left_col_configs:w}}};var n,r,i;e.parameters={...e.parameters,docs:{...(n=e.parameters)==null?void 0:n.docs,source:{originalSource:`{
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
}`,...(i=(r=e.parameters)==null?void 0:r.docs)==null?void 0:i.source}}};const O=["Primary"];export{e as Primary,O as __namedExportsOrder,E as default};
