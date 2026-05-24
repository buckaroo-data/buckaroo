import{j as o}from"./jsx-runtime-DiklIkkE.js";import{r as n}from"./index-DRjF_FHU.js";import{D as U}from"./BuckarooWidgetInfinite-CZlls-5x.js";import{K as X}from"./SmartRowCache-BVioPz_d.js";import"./ColumnsEditor-DQtkvnon.js";import"./Operations-wB0ylO1l.js";import"./_baseEach-B-y44WsN.js";import"./isArray-Dxzbedgu.js";import"./isString-CNnovG4X.js";import"./clone-ZfB6SeuH.js";import"./OperationsList-CPVzoTey.js";import"./gridUtils-DA3Cr0Lp.js";import"./main.esm-pliBxWka.js";import"./HistogramCell-qbNrk3qL.js";import"./index-DIvcuAjW.js";import"./ChartCell-DjlNlKxO.js";import"./tiny-invariant-CopsF_GD.js";import"./StatusBar-DZymaJXX.js";import"./index.esm-sPCRP4vH.js";import"./fromPairs-Dx9PT-t0.js";import"./DFViewerInfinite-CA9XM3VM.js";import"./MessageBox-DNTFc2vJ.js";function Z(e){return Array.from({length:e},(r,t)=>({index:t,a:t*10,b:`row_${t}`}))}function ee(e){const r=Z(e),t=new X(a=>{const s=Math.min(a.end,e);if(s<=a.start)return;const f={key:a,data:r.slice(a.start,s),length:e};setTimeout(()=>t.addPayloadResponse(f),5)});return t}function te(e){return{main:{data_key:"main",df_viewer_config:{pinned_rows:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"string"}}],column_config:[{col_name:"a",header_name:"a",displayer_args:{displayer:"integer",min_digits:1,max_digits:5}},{col_name:"b",header_name:"b",displayer_args:{displayer:"obj"}}],component_config:e?{layoutType:"autoHeight"}:void 0},summary_stats_key:"all_stats"}}}const re=({autoHeight:e,children:r})=>{const t=e?{width:"100%"}:{width:"100%",height:"100%"};return o.jsx("div",{className:"buckaroo_anywidget",style:t,"data-testid":"bk-wrapper",children:r})},S=({rowCount:e,autoHeight:r,label:t})=>{const a=n.useMemo(()=>ee(e),[e]),s=n.useMemo(()=>({total_rows:e,columns:2,filtered_rows:e,rows_shown:e}),[e]),f=n.useMemo(()=>te(r),[r]),Q=n.useMemo(()=>({}),[]);return o.jsxs(re,{autoHeight:r,children:[t!==void 0?o.jsxs("div",{"data-testid":`cell-label-${t}`,style:{fontSize:11,padding:"2px 6px",color:"#888"},children:[t," — ",e," rows, autoHeight=",String(r)]}):null,o.jsx(U,{df_meta:s,df_data_dict:Q,df_display_args:f,src:a,df_id:`height-test-${e}-${r}`})]})},oe=({rowCount:e,autoHeight:r,hostHeight:t})=>o.jsx("div",{"data-testid":"host",style:{width:720,height:t,border:"2px solid red",boxSizing:"border-box",overflow:"hidden"},children:o.jsx(S,{rowCount:e,autoHeight:r})}),J=({rowCounts:e,autoHeight:r,hostHeight:t})=>o.jsxs("div",{"data-testid":"host",style:{width:720,height:t,border:"2px solid red",boxSizing:"border-box",overflowY:"auto",display:"flex",flexDirection:"column",gap:8,padding:8},children:[o.jsx("div",{"data-testid":"stack-cell-0",style:{border:"1px dashed #888"},children:o.jsx(S,{rowCount:e[0],autoHeight:r,label:"cell-0"})}),o.jsx("div",{"data-testid":"stack-cell-1",style:{border:"1px dashed #888"},children:o.jsx(S,{rowCount:e[1],autoHeight:r,label:"cell-1"})})]}),je={title:"Buckaroo/Height/BuckarooView",component:oe,parameters:{layout:"fullscreen"},argTypes:{rowCount:{control:{type:"number",min:1,max:5e3,step:1}},autoHeight:{control:"boolean"},hostHeight:{control:{type:"number",min:100,max:2e3,step:10}}}},i={args:{rowCount:3,autoHeight:!1,hostHeight:700}},c={args:{rowCount:3,autoHeight:!0,hostHeight:700}},d={args:{rowCount:2e3,autoHeight:!1,hostHeight:700}},g={args:{rowCount:2e3,autoHeight:!0,hostHeight:700}},l={args:{rowCount:3,autoHeight:!1,hostHeight:400}},m={args:{rowCount:3,autoHeight:!0,hostHeight:400}},h={args:{rowCount:2e3,autoHeight:!1,hostHeight:400}},u={args:{rowCount:2e3,autoHeight:!0,hostHeight:400}},p={render:e=>o.jsx(J,{...e}),args:{rowCounts:[4,200],autoHeight:!0,hostHeight:900}},H={render:e=>o.jsx(J,{...e}),args:{rowCounts:[4,200],autoHeight:!1,hostHeight:900}};var x,w,_;i.parameters={...i.parameters,docs:{...(x=i.parameters)==null?void 0:x.docs,source:{originalSource:`{
  args: {
    rowCount: 3,
    autoHeight: false,
    hostHeight: 700
  }
}`,...(_=(w=i.parameters)==null?void 0:w.docs)==null?void 0:_.source}}};var y,k,D;c.parameters={...c.parameters,docs:{...(y=c.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    rowCount: 3,
    autoHeight: true,
    hostHeight: 700
  }
}`,...(D=(k=c.parameters)==null?void 0:k.docs)==null?void 0:D.source}}};var b,j,C;d.parameters={...d.parameters,docs:{...(b=d.parameters)==null?void 0:b.docs,source:{originalSource:`{
  args: {
    rowCount: 2000,
    autoHeight: false,
    hostHeight: 700
  }
}`,...(C=(j=d.parameters)==null?void 0:j.docs)==null?void 0:C.source}}};var A,L,v;g.parameters={...g.parameters,docs:{...(A=g.parameters)==null?void 0:A.docs,source:{originalSource:`{
  args: {
    rowCount: 2000,
    autoHeight: true,
    hostHeight: 700
  }
}`,...(v=(L=g.parameters)==null?void 0:L.docs)==null?void 0:v.source}}};var F,M,E;l.parameters={...l.parameters,docs:{...(F=l.parameters)==null?void 0:F.docs,source:{originalSource:`{
  args: {
    rowCount: 3,
    autoHeight: false,
    hostHeight: 400
  }
}`,...(E=(M=l.parameters)==null?void 0:M.docs)==null?void 0:E.source}}};var R,$,z;m.parameters={...m.parameters,docs:{...(R=m.parameters)==null?void 0:R.docs,source:{originalSource:`{
  args: {
    rowCount: 3,
    autoHeight: true,
    hostHeight: 400
  }
}`,...(z=($=m.parameters)==null?void 0:$.docs)==null?void 0:z.source}}};var B,T,V;h.parameters={...h.parameters,docs:{...(B=h.parameters)==null?void 0:B.docs,source:{originalSource:`{
  args: {
    rowCount: 2000,
    autoHeight: false,
    hostHeight: 400
  }
}`,...(V=(T=h.parameters)==null?void 0:T.docs)==null?void 0:V.source}}};var K,I,N;u.parameters={...u.parameters,docs:{...(K=u.parameters)==null?void 0:K.docs,source:{originalSource:`{
  args: {
    rowCount: 2000,
    autoHeight: true,
    hostHeight: 400
  }
}`,...(N=(I=u.parameters)==null?void 0:I.docs)==null?void 0:N.source}}};var O,P,W;p.parameters={...p.parameters,docs:{...(O=p.parameters)==null?void 0:O.docs,source:{originalSource:`{
  render: (args: StackedArgs) => <Stacked {...args} />,
  args: {
    rowCounts: [4, 200],
    autoHeight: true,
    hostHeight: 900
  }
}`,...(W=(P=p.parameters)==null?void 0:P.docs)==null?void 0:W.source}}};var Y,q,G;H.parameters={...H.parameters,docs:{...(Y=H.parameters)==null?void 0:Y.docs,source:{originalSource:`{
  render: (args: StackedArgs) => <Stacked {...args} />,
  args: {
    rowCounts: [4, 200],
    autoHeight: false,
    hostHeight: 900
  }
}`,...(G=(q=H.parameters)==null?void 0:q.docs)==null?void 0:G.source}}};const Ce=["SmallDfFixed","SmallDfAutoHeight","LargeDfFixed","LargeDfAutoHeight","SmallDfShortHostFixed","SmallDfShortHostAutoHeight","LargeDfShortHostFixed","LargeDfShortHostAutoHeight","StackedAutoHeightSmallLarge","StackedFixedSmallLarge"];export{g as LargeDfAutoHeight,d as LargeDfFixed,u as LargeDfShortHostAutoHeight,h as LargeDfShortHostFixed,c as SmallDfAutoHeight,i as SmallDfFixed,m as SmallDfShortHostAutoHeight,l as SmallDfShortHostFixed,p as StackedAutoHeightSmallLarge,H as StackedFixedSmallLarge,Ce as __namedExportsOrder,je as default};
