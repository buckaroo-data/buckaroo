import{j as c}from"./jsx-runtime-DiklIkkE.js";import{r as x}from"./index-DRjF_FHU.js";import{a as z}from"./gridUtils-CtUjoyZk.js";import"./lodash-CGIzQN7T.js";import"./HistogramCell-CrXfgV_n.js";import"./index-Bx0Ph3cE.js";import"./ChartCell-ClfxlV_N.js";import"./tiny-invariant-CopsF_GD.js";import"./main.esm-B8BDqAWP.js";const G=(o,r,_=0,n,i=!1)=>({rowCount:Math.max(o.length,r.length),getRows(e){var S;const t=JSON.stringify((S=e.context)==null?void 0:S.outside_df_params),l=t!=null&&t.includes('"key":"B"')?"B":"A",u=l==="B"?r:o,a=i?[...u]:u,[s]=e.sortModel||[];if(i&&(s!=null&&s.colId)&&(s!=null&&s.sort)){const{colId:k,sort:q}=s;a.sort((f,h)=>{const d=f==null?void 0:f[k],m=h==null?void 0:h[k];if(d===m)return 0;if(d===void 0)return 1;if(m===void 0)return-1;const v=typeof d=="number"&&typeof m=="number"?d-m:String(d).localeCompare(String(m));return q==="asc"?v:-v})}const p=(n==null?void 0:n[l])??_,D=a.slice(e.startRow,e.endRow);p>0?setTimeout(()=>e.successCallback(D,a.length),p):e.successCallback(D,a.length)}}),H=(o,r)=>({datasource:o,data_type:"DataSource",length:r}),L={column_config:[{col_name:"a",header_name:"a",displayer_args:{displayer:"obj"}},{col_name:"b",header_name:"b",displayer_args:{displayer:"obj"}}],pinned_rows:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"string"}}]},Q=[{a:"A1",b:"A"},{a:"A2",b:"A"},{a:"A3",b:"A"}],U=[{a:"B1",b:"B"},{a:"B2",b:"B"},{a:"B3",b:"B"}],X=[{a:"A3",b:"A"},{a:"A1",b:"A"},{a:"A2",b:"A"}],Y=[{a:"B3",b:"B"},{a:"B1",b:"B"},{a:"B2",b:"B"}],Z=({delayed:o,delayByKey:r,dataVariant:_="default",enableSort:n=!1})=>{const[i,w]=x.useState({key:"A"}),[e,t]=_==="sortable"?[X,Y]:[Q,U],l=x.useMemo(()=>G(e,t,o?150:0,r,n),[e,t,o,r,n]),u=x.useMemo(()=>H(l,Math.max(e.length,t.length)),[l,e.length,t.length]),a=()=>w(p=>({key:p.key==="A"?"B":"A"})),s=()=>{setTimeout(a,0),setTimeout(a,40),setTimeout(a,80)};return c.jsxs("div",{style:{height:420,width:520},children:[c.jsxs("div",{style:{marginBottom:8,display:"flex",gap:8},children:[c.jsx("button",{onClick:a,children:"Toggle Params"}),c.jsx("button",{onClick:s,children:"Rapid Toggle x3"}),c.jsxs("span",{"data-testid":"outside-key",children:["outside_df_params.key = ",i.key]})]}),c.jsx(z,{data_wrapper:u,df_viewer_config:L,summary_stats_data:[],outside_df_params:i,activeCol:["",""],setActiveCol:()=>{},error_info:""})]})},ie={title:"Buckaroo/DFViewer/OutsideParamsInconsistency",component:Z,parameters:{layout:"centered"},tags:["autodocs"]},g={args:{delayed:!1}},y={args:{delayed:!0}},A={args:{delayByKey:{A:1200,B:40}}},B={args:{delayByKey:{A:40,B:1200}}},b={args:{delayByKey:{A:500,B:50},dataVariant:"sortable",enableSort:!0}};var C,j,T;g.parameters={...g.parameters,docs:{...(C=g.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    delayed: false
  }
}`,...(T=(j=g.parameters)==null?void 0:j.docs)==null?void 0:T.source}}};var F,M,O;y.parameters={...y.parameters,docs:{...(F=y.parameters)==null?void 0:F.docs,source:{originalSource:`{
  args: {
    delayed: true
  }
}`,...(O=(M=y.parameters)==null?void 0:M.docs)==null?void 0:O.source}}};var R,I,P;A.parameters={...A.parameters,docs:{...(R=A.parameters)==null?void 0:R.docs,source:{originalSource:`{
  args: {
    delayByKey: {
      A: 1200,
      B: 40
    }
  }
}`,...(P=(I=A.parameters)==null?void 0:I.docs)==null?void 0:P.source}}};var V,E,K;B.parameters={...B.parameters,docs:{...(V=B.parameters)==null?void 0:V.docs,source:{originalSource:`{
  args: {
    delayByKey: {
      A: 40,
      B: 1200
    }
  }
}`,...(K=(E=B.parameters)==null?void 0:E.docs)==null?void 0:K.source}}};var W,J,N;b.parameters={...b.parameters,docs:{...(W=b.parameters)==null?void 0:W.docs,source:{originalSource:`{
  args: {
    delayByKey: {
      A: 500,
      B: 50
    },
    dataVariant: "sortable",
    enableSort: true
  }
}`,...(N=(J=b.parameters)==null?void 0:J.docs)==null?void 0:N.source}}};const le=["Primary","WithDelay","AsymmetricDelayASlowBFast","AsymmetricDelayBSlowAFast","SortAndToggle"];export{A as AsymmetricDelayASlowBFast,B as AsymmetricDelayBSlowAFast,g as Primary,b as SortAndToggle,y as WithDelay,le as __namedExportsOrder,ie as default};
