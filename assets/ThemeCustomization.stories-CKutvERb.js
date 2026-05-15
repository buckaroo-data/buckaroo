import{j as i}from"./jsx-runtime-DiklIkkE.js";import{a as j}from"./DFViewerInfinite-B6tFdgBl.js";import"./index-DRjF_FHU.js";import"./gridUtils-LxDV4unU.js";import"./main.esm-C6PYKVYP.js";import"./_baseEach-B-y44WsN.js";import"./isArray-Dxzbedgu.js";import"./HistogramCell-qbNrk3qL.js";import"./index-DIvcuAjW.js";import"./ChartCell-DjlNlKxO.js";import"./tiny-invariant-CopsF_GD.js";import"./isString-CNnovG4X.js";import"./index.esm-D_s6Kf8n.js";const T=({data_wrapper:a,df_viewer_config:S})=>{const y=F=>{console.log("defaultSetColumnFunc",F)};return i.jsx("div",{style:{height:500,width:800},children:i.jsx(j,{data_wrapper:a,df_viewer_config:S,setActiveCol:y})})},M={title:"Buckaroo/Theme/ThemeCustomization",component:T,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},I={col_name:"index",header_name:"index",displayer_args:{displayer:"string"}},N=[I],d=[{index:"0",a:10,b:"foo",c:100},{index:"1",a:20,b:"bar",c:200},{index:"2",a:30,b:"baz",c:300},{index:"3",a:40,b:"qux",c:400},{index:"4",a:50,b:"quux",c:500}],e={data_type:"Raw",data:d,length:d.length},R=[{col_name:"a",header_name:"a",displayer_args:{displayer:"integer",min_digits:1,max_digits:5}},{col_name:"b",header_name:"b",displayer_args:{displayer:"obj"}},{col_name:"c",header_name:"c",displayer_args:{displayer:"integer",min_digits:1,max_digits:5}}];function r(a){return{column_config:R,pinned_rows:[],left_col_configs:N,component_config:a?{theme:a}:void 0}}const o={args:{data_wrapper:e,df_viewer_config:r()}},n={args:{data_wrapper:e,df_viewer_config:r({accentColor:"#ff6600"})}},t={args:{data_wrapper:e,df_viewer_config:r({colorScheme:"dark",backgroundColor:"#1a1a2e"})}},c={args:{data_wrapper:e,df_viewer_config:r({colorScheme:"light",backgroundColor:"#fafafa"})}},s={args:{data_wrapper:e,df_viewer_config:r({colorScheme:"dark",accentColor:"#e91e63",accentHoverColor:"#c2185b",backgroundColor:"#1a1a2e",foregroundColor:"#e0e0e0",oddRowBackgroundColor:"#16213e",borderColor:"#0f3460"})}};var m,p,l;o.parameters={...o.parameters,docs:{...(m=o.parameters)==null?void 0:m.docs,source:{originalSource:`{
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig()
  }
}`,...(l=(p=o.parameters)==null?void 0:p.docs)==null?void 0:l.source}}};var g,f,u;n.parameters={...n.parameters,docs:{...(g=n.parameters)==null?void 0:g.docs,source:{originalSource:`{
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      accentColor: '#ff6600'
    })
  }
}`,...(u=(f=n.parameters)==null?void 0:f.docs)==null?void 0:u.source}}};var _,C,w;t.parameters={...t.parameters,docs:{...(_=t.parameters)==null?void 0:_.docs,source:{originalSource:`{
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      colorScheme: 'dark',
      backgroundColor: '#1a1a2e'
    })
  }
}`,...(w=(C=t.parameters)==null?void 0:C.docs)==null?void 0:w.source}}};var h,b,k;c.parameters={...c.parameters,docs:{...(h=c.parameters)==null?void 0:h.docs,source:{originalSource:`{
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      colorScheme: 'light',
      backgroundColor: '#fafafa'
    })
  }
}`,...(k=(b=c.parameters)==null?void 0:b.docs)==null?void 0:k.source}}};var x,v,D;s.parameters={...s.parameters,docs:{...(x=s.parameters)==null?void 0:x.docs,source:{originalSource:`{
  args: {
    data_wrapper: rawData,
    df_viewer_config: makeConfig({
      colorScheme: 'dark',
      accentColor: '#e91e63',
      accentHoverColor: '#c2185b',
      backgroundColor: '#1a1a2e',
      foregroundColor: '#e0e0e0',
      oddRowBackgroundColor: '#16213e',
      borderColor: '#0f3460'
    })
  }
}`,...(D=(v=s.parameters)==null?void 0:v.docs)==null?void 0:D.source}}};const P=["DefaultNoTheme","CustomAccent","ForcedDark","ForcedLight","FullCustom"];export{n as CustomAccent,o as DefaultNoTheme,t as ForcedDark,c as ForcedLight,s as FullCustom,P as __namedExportsOrder,M as default};
