import{j as l}from"./jsx-runtime-DiklIkkE.js";import{r as se}from"./index-DRjF_FHU.js";import{a as de}from"./DFViewerInfinite-DAb2c3VM.js";import"./gridUtils-CTYRA-Q8.js";import"./main.esm-KSBVO7T_.js";import"./_baseEach-C9E3e27i.js";import"./isArray-Dxzbedgu.js";import"./HistogramCell-D_CuDgeo.js";import"./index-DIvcuAjW.js";import"./ChartCell-DjlNlKxO.js";import"./tiny-invariant-CopsF_GD.js";import"./isString-SHB7N511.js";import"./index.esm-Br-1or4R.js";const _=[{index:0,name:"Alice",value:42.5},{index:1,name:"Bob",value:73.1},{index:2,name:"Charlie",value:19.8},{index:3,name:"Diana",value:88},{index:4,name:"Eve",value:55.3}],g=Array.from({length:500},(e,t)=>({index:t,name:`row_${String(t).padStart(3,"0")}`,value:parseFloat((Math.sin(t*.1)*100).toFixed(2))})),re=["dtype","count","unique","mean","std","min","25%","50%","75%","max"],ae=re.map(e=>({index:e,name:e==="dtype"?"object":"—",value:e==="dtype"?"float64":e==="count"?500:"—"})),te=re.map(e=>({primary_key_val:e,displayer_args:{displayer:"obj"}}));function r(e){return{data_type:"Raw",data:e,length:e.length}}function a(e=[],t){return{column_config:[{col_name:"name",header_name:"Name",displayer_args:{displayer:"obj"}},{col_name:"value",header_name:"Value",displayer_args:{displayer:"float",min_fraction_digits:1,max_fraction_digits:2}}],pinned_rows:e,left_col_configs:[{col_name:"index",header_name:"#",displayer_args:{displayer:"obj"}}],component_config:t}}const ce=({data_wrapper:e,df_viewer_config:t,summary_stats_data:oe,outerHeight:ne})=>{const ie=se.useCallback(()=>{},[]);return l.jsx("div",{style:{border:"3px solid red",width:800,height:ne,boxSizing:"border-box"},children:l.jsx(de,{data_wrapper:e,df_viewer_config:t,summary_stats_data:oe,setActiveCol:ie})})},Ee={title:"Docs/Height Modes",component:ce,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{data_wrapper:{control:!1},df_viewer_config:{control:!1},summary_stats_data:{control:!1},outerHeight:{control:{type:"number"},description:"Outer container height (px)"}}},o={args:{data_wrapper:r(_),df_viewer_config:a()}},n={args:{data_wrapper:r(_),df_viewer_config:a(te),summary_stats_data:ae}},i={args:{data_wrapper:r(g),df_viewer_config:a([],{dfvHeight:400}),outerHeight:400}},s={args:{data_wrapper:r(g),df_viewer_config:a(te,{dfvHeight:400}),summary_stats_data:ae,outerHeight:400}},d={args:{data_wrapper:r(g),df_viewer_config:a([],{dfvHeight:200}),outerHeight:200}},c={args:{data_wrapper:r(g),df_viewer_config:a([],{height_fraction:4}),outerHeight:300}},p={args:{data_wrapper:r(g),df_viewer_config:a([],{layoutType:"autoHeight"})}},m={args:{data_wrapper:r(_),df_viewer_config:a([],{layoutType:"normal",dfvHeight:300}),outerHeight:300}};var h,u,f,w,v;o.parameters={...o.parameters,docs:{...(h=o.parameters)==null?void 0:h.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_ROW_DATA),
    df_viewer_config: makeConfig()
  }
}`,...(f=(u=o.parameters)==null?void 0:u.docs)==null?void 0:f.source},description:{story:'5 rows fit without scrolling, so Buckaroo auto-detects `shortMode` and\nswitches to `domLayout: "autoHeight"`. The grid and outer container grow to\ncontent height — no explicit sizing needed.',...(v=(w=o.parameters)==null?void 0:w.docs)==null?void 0:v.description}}};var y,H,T,E,R;n.parameters={...n.parameters,docs:{...(y=n.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_ROW_DATA),
    df_viewer_config: makeConfig(TEN_PINNED),
    summary_stats_data: TEN_PINNED_STATS
  }
}`,...(T=(H=n.parameters)==null?void 0:H.docs)==null?void 0:T.source},description:{story:"Pinned rows count toward the `shortMode` threshold. 10 pinned stat rows +\n5 data rows still fit without scrolling, so `autoHeight` is still\nauto-detected. Pinned rows appear above the scrollable data area.",...(R=(E=n.parameters)==null?void 0:E.docs)==null?void 0:R.description}}};var x,D,A,F,N;i.parameters={...i.parameters,docs:{...(x=i.parameters)==null?void 0:x.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
    df_viewer_config: makeConfig([], {
      dfvHeight: 400
    }),
    outerHeight: 400
  }
}`,...(A=(D=i.parameters)==null?void 0:D.docs)==null?void 0:A.source},description:{story:'500 rows exceed the scroll threshold, so Buckaroo switches to\n`domLayout: "normal"` with a fixed height. Here `dfvHeight: 400` is set\nexplicitly and the outer container matches.',...(N=(F=i.parameters)==null?void 0:F.docs)==null?void 0:N.description}}};var k,S,b,I,V;s.parameters={...s.parameters,docs:{...(k=s.parameters)==null?void 0:k.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
    df_viewer_config: makeConfig(TEN_PINNED, {
      dfvHeight: 400
    }),
    summary_stats_data: TEN_PINNED_STATS,
    outerHeight: 400
  }
}`,...(b=(S=s.parameters)==null?void 0:S.docs)==null?void 0:b.source},description:{story:"500 rows in `normal` mode with 10 stat rows pinned to the top of the grid.\nPinned rows stay visible while data rows scroll beneath them.",...(V=(I=s.parameters)==null?void 0:I.docs)==null?void 0:V.description}}};var P,C,O,W,j;d.parameters={...d.parameters,docs:{...(P=d.parameters)==null?void 0:P.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
    df_viewer_config: makeConfig([], {
      dfvHeight: 200
    }),
    outerHeight: 200
  }
}`,...(O=(C=d.parameters)==null?void 0:C.docs)==null?void 0:O.source},description:{story:"`component_config.dfvHeight` sets an explicit pixel height for the grid,\noverriding the default of `window.innerHeight / 2`. Set the outer container\nto the same value. Here `dfvHeight: 200` makes a compact embed.",...(j=(W=d.parameters)==null?void 0:W.docs)==null?void 0:j.description}}};var U,M,z,B,L;c.parameters={...c.parameters,docs:{...(U=c.parameters)==null?void 0:U.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
    df_viewer_config: makeConfig([], {
      height_fraction: 4
    }),
    outerHeight: 300
  }
}`,...(z=(M=c.parameters)==null?void 0:M.docs)==null?void 0:z.source},description:{story:"`component_config.height_fraction = 4` sets `dfvHeight = window.innerHeight / 4`.\nThe grid height tracks the browser window — resize to see it update.",...(L=(B=c.parameters)==null?void 0:B.docs)==null?void 0:L.description}}};var q,$,G,J,K;p.parameters={...p.parameters,docs:{...(q=p.parameters)==null?void 0:q.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_HUNDRED_ROW_DATA),
    df_viewer_config: makeConfig([], {
      layoutType: "autoHeight"
    })
  }
}`,...(G=($=p.parameters)==null?void 0:$.docs)==null?void 0:G.source},description:{story:'`component_config.layoutType: "autoHeight"` forces the grid to grow to all\nrows regardless of count. Use only in hosts where vertical space is\nunconstrained (e.g. a notebook-style cell stack).',...(K=(J=p.parameters)==null?void 0:J.docs)==null?void 0:K.description}}};var Q,X,Y,Z,ee;m.parameters={...m.parameters,docs:{...(Q=m.parameters)==null?void 0:Q.docs,source:{originalSource:`{
  args: {
    data_wrapper: makeRaw(FIVE_ROW_DATA),
    df_viewer_config: makeConfig([], {
      layoutType: "normal",
      dfvHeight: 300
    }),
    outerHeight: 300
  }
}`,...(Y=(X=m.parameters)==null?void 0:X.docs)==null?void 0:Y.source},description:{story:'`component_config.layoutType: "normal"` forces a fixed-height grid even for\nsmall datasets. Useful for fixed-height panels (e.g. an entry-detail sidebar)\nwhere the embed must not resize with the data. See also the `autoHeight` prop\non `BuckarooServerView` / `DFViewerInfiniteDS`, fixed in #862.',...(ee=(Z=m.parameters)==null?void 0:Z.docs)==null?void 0:ee.description}}};const Re=["FiveRows","FiveRowsTenPinned","FiveHundredRows","FiveHundredRowsTenPinned","ExplicitHeight200","HeightFraction4","ForceAutoHeight","ForceNormal"];export{d as ExplicitHeight200,i as FiveHundredRows,s as FiveHundredRowsTenPinned,o as FiveRows,n as FiveRowsTenPinned,p as ForceAutoHeight,m as ForceNormal,c as HeightFraction4,Re as __namedExportsOrder,Ee as default};
