import{j as o}from"./jsx-runtime-DiklIkkE.js";/* empty css                */import{S as y}from"./StatusBar-CFyHlEdB.js";import{r as w}from"./index-DRjF_FHU.js";import"./index.esm-Br-1or4R.js";import"./main.esm-KSBVO7T_.js";import"./_baseEach-C9E3e27i.js";import"./isArray-Dxzbedgu.js";import"./index-DIvcuAjW.js";import"./gridUtils-BcZQCEEY.js";import"./HistogramCell-BcczClGD.js";import"./ChartCell-Dl5MZ_x9.js";import"./tiny-invariant-CopsF_GD.js";import"./isString-SHB7N511.js";import"./fromPairs-Dx9PT-t0.js";import"./clone-BO-PRgF1.js";const O=({dfMeta:b,buckarooState:h,buckarooOptions:S,inFlight:k})=>{const[n,x]=w.useState(h);return o.jsxs("div",{className:"dcf-root flex flex-col",style:{width:"800px",height:"300px",border:"1px solid red"},children:[o.jsx("div",{className:"orig-df",style:{overflow:"hidden"},children:o.jsx(y,{dfMeta:b,buckarooState:n,setBuckarooState:x,buckarooOptions:S,heightOverride:150,inFlight:k})}),o.jsxs("pre",{children:[" ",JSON.stringify(n,void 0,4)]})]})},A={title:"Buckaroo/StatusBar",component:O,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},r={total_rows:378,columns:7,filtered_rows:297,rows_shown:297},_={sampled:["sample_strat1","sample_strat2",""],cleaning_method:["clean_strat1","clean_strat2",""],post_processing:["","post1","post2"],df_display:["main","summary"],show_commands:["on","off"]},e={sampled:!1,cleaning_method:!1,quick_command_args:{},post_processing:!1,df_display:"main",show_commands:!1},s={args:{dfMeta:r,buckarooState:e,buckarooOptions:_}},a={args:{dfMeta:r,buckarooState:e,buckarooOptions:{sampled:["sample_strat1","sample_strat2",""],cleaning_method:[],post_processing:[],df_display:["main","summary"],show_commands:["on","off"]}}},t={args:{dfMeta:r,buckarooState:e,buckarooOptions:_,inFlight:!0}};var m,i,c;s.parameters={...s.parameters,docs:{...(m=s.parameters)==null?void 0:m.docs,source:{originalSource:`{
  args: {
    dfMeta: dfm,
    buckarooState: bs,
    buckarooOptions: bo
  }
}`,...(c=(i=s.parameters)==null?void 0:i.docs)==null?void 0:c.source}}};var p,d,l;a.parameters={...a.parameters,docs:{...(p=a.parameters)==null?void 0:p.docs,source:{originalSource:`{
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
}`,...(l=(d=a.parameters)==null?void 0:d.docs)==null?void 0:l.source}}};var u,f,g;t.parameters={...t.parameters,docs:{...(u=t.parameters)==null?void 0:u.docs,source:{originalSource:`{
  args: {
    dfMeta: dfm,
    buckarooState: bs,
    buckarooOptions: bo,
    inFlight: true
  }
}`,...(g=(f=t.parameters)==null?void 0:f.docs)==null?void 0:g.source}}};const D=["Primary","NoCleaningNoPostProcessing","InFlight"];export{t as InFlight,a as NoCleaningNoPostProcessing,s as Primary,D as __namedExportsOrder,A as default};
