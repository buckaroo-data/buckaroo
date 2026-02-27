import{j as s}from"./jsx-runtime-DiklIkkE.js";/* empty css                */import{S as g}from"./StatusBar-CtQBasjn.js";import{r as h}from"./index-DRjF_FHU.js";import"./lodash-CGIzQN7T.js";import"./main.esm-B8BDqAWP.js";import"./index-Bx0Ph3cE.js";import"./gridUtils-BzTbwOwX.js";import"./HistogramCell-CrXfgV_n.js";import"./ChartCell-ClfxlV_N.js";import"./tiny-invariant-CopsF_GD.js";const b=({dfMeta:l,buckarooState:f,buckarooOptions:u})=>{const[t,_]=h.useState(f);return s.jsxs("div",{className:"dcf-root flex flex-col",style:{width:"800px",height:"300px",border:"1px solid red"},children:[s.jsx("div",{className:"orig-df",style:{overflow:"hidden"},children:s.jsx(g,{dfMeta:l,buckarooState:t,setBuckarooState:_,buckarooOptions:u,heightOverride:150})}),s.jsxs("pre",{children:[" ",JSON.stringify(t,void 0,4)]})]})},E={title:"Buckaroo/StatusBar",component:b,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},p={total_rows:378,columns:7,filtered_rows:297,rows_shown:297},S={sampled:["sample_strat1","sample_strat2",""],cleaning_method:["clean_strat1","clean_strat2",""],post_processing:["","post1","post2"],df_display:["main","summary"],show_commands:["on","off"]},d={sampled:!1,cleaning_method:!1,quick_command_args:{},post_processing:!1,df_display:"main",show_commands:!1},o={args:{dfMeta:p,buckarooState:d,buckarooOptions:S}},a={args:{dfMeta:p,buckarooState:d,buckarooOptions:{sampled:["sample_strat1","sample_strat2",""],cleaning_method:[],post_processing:[],df_display:["main","summary"],show_commands:["on","off"]}}};var r,e,n;o.parameters={...o.parameters,docs:{...(r=o.parameters)==null?void 0:r.docs,source:{originalSource:`{
  args: {
    dfMeta: dfm,
    buckarooState: bs,
    buckarooOptions: bo
  }
}`,...(n=(e=o.parameters)==null?void 0:e.docs)==null?void 0:n.source}}};var m,c,i;a.parameters={...a.parameters,docs:{...(m=a.parameters)==null?void 0:m.docs,source:{originalSource:`{
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
}`,...(i=(c=a.parameters)==null?void 0:c.docs)==null?void 0:i.source}}};const C=["Primary","NoCleaningNoPostProcessing"];export{a as NoCleaningNoPostProcessing,o as Primary,C as __namedExportsOrder,E as default};
