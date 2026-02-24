import{j as s}from"./jsx-runtime-DiklIkkE.js";/* empty css                */import{S as g}from"./StatusBar-yCS5yqoM.js";import{r as h}from"./index-DRjF_FHU.js";import"./index.esm-Bddaha_j.js";import"./_baseEach-B-y44WsN.js";import"./isArray-Dxzbedgu.js";import"./index-DIvcuAjW.js";import"./gridUtils-Bgxku6QU.js";import"./HistogramCell-Bzivjlh2.js";import"./ChartCell-BfPIzAg-.js";import"./tiny-invariant-CopsF_GD.js";import"./isString-CNnovG4X.js";import"./fromPairs-Dx9PT-t0.js";import"./clone-ZfB6SeuH.js";const b=({dfMeta:l,buckarooState:f,buckarooOptions:u})=>{const[t,_]=h.useState(f);return s.jsxs("div",{className:"dcf-root flex flex-col",style:{width:"800px",height:"300px",border:"1px solid red"},children:[s.jsx("div",{className:"orig-df",style:{overflow:"hidden"},children:s.jsx(g,{dfMeta:l,buckarooState:t,setBuckarooState:_,buckarooOptions:u,heightOverride:150})}),s.jsxs("pre",{children:[" ",JSON.stringify(t,void 0,4)]})]})},R={title:"Buckaroo/StatusBar",component:b,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},c={total_rows:378,columns:7,filtered_rows:297,rows_shown:297},S={sampled:["sample_strat1","sample_strat2",""],cleaning_method:["clean_strat1","clean_strat2",""],post_processing:["","post1","post2"],df_display:["main","summary"],show_commands:["on","off"]},d={sampled:!1,cleaning_method:!1,quick_command_args:{},post_processing:!1,df_display:"main",show_commands:!1},o={args:{dfMeta:c,buckarooState:d,buckarooOptions:S}},a={args:{dfMeta:c,buckarooState:d,buckarooOptions:{sampled:["sample_strat1","sample_strat2",""],cleaning_method:[],post_processing:[],df_display:["main","summary"],show_commands:["on","off"]}}};var r,e,n;o.parameters={...o.parameters,docs:{...(r=o.parameters)==null?void 0:r.docs,source:{originalSource:`{
  args: {
    dfMeta: dfm,
    buckarooState: bs,
    buckarooOptions: bo
  }
}`,...(n=(e=o.parameters)==null?void 0:e.docs)==null?void 0:n.source}}};var m,i,p;a.parameters={...a.parameters,docs:{...(m=a.parameters)==null?void 0:m.docs,source:{originalSource:`{
  args: {
    dfMeta: dfm,
    buckarooState: bs,
    buckarooOptions: {
      sampled: ["sample_strat1", "sample_strat2", ""],
      cleaning_method: [],
      post_processing: [],
      df_display: ["main", "summary"],
      show_commands: ["on", "off"]
    }
  }
}`,...(p=(i=a.parameters)==null?void 0:i.docs)==null?void 0:p.source}}};const T=["Primary","NoCleaningNoPostProcessing"];export{a as NoCleaningNoPostProcessing,o as Primary,T as __namedExportsOrder,R as default};
