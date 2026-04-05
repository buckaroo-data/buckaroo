import{j as e}from"./jsx-runtime-DiklIkkE.js";import{r as s}from"./index-DRjF_FHU.js";import{c as S}from"./DFViewerDataHelper-avTK4TER.js";import{a as p}from"./StoryUtils-CpZZKZSs.js";import{A as x,t as w,c as y}from"./index.esm-DceZDocr.js";import"./_baseEach-B-y44WsN.js";import"./isArray-Dxzbedgu.js";import"./client-vn2d2opv.js";import"./index-BKlBQwGM.js";const v=w.withPart(y).withParams({spacing:5,browserColorScheme:"dark",cellHorizontalPaddingScale:.3,columnBorder:!0,rowBorder:!1,rowVerticalPaddingScale:.5,wrapperBorder:!1,fontSize:12,dataFontSize:"12px",headerFontSize:14,iconSize:10,backgroundColor:"#181D1F",oddRowBackgroundColor:"#222628",headerVerticalPaddingScale:.6}),j=({colDefs:t,data:o,datasource:r,extra_context:c})=>{const l=new Date;console.log("SubComponent, rendered",new Date-1);const d={cellStyle:a=>{var g;const f=a.column.getColDef().field;return((g=a.context)==null?void 0:g.activeCol)===f?{background:"green"}:{background:"red"}}},m={onFirstDataRendered:a=>{console.log(`[DFViewerInfinite] AG-Grid finished rendering at ${new Date().toISOString()}`),console.log(`[DFViewerInfinite] Total render time: ${Date.now()-l}ms`)},domLayout:"normal",autoSizeStrategy:{type:"fitCellContents"},rowBuffer:20,rowModelType:"infinite",cacheBlockSize:10+50,cacheOverflowSize:0,maxConcurrentDatasourceRequests:2,maxBlocksInCache:0,infiniteInitialRowCount:0};return e.jsx("div",{style:{border:"1px solid purple",height:"500px"},children:e.jsx(x,{columnDefs:t,rowData:o,theme:v,datasource:r.datasource,rowModelType:"infinite",defaultColDef:d,context:c,gridOptions:m,loadThemeGoogleFonts:!0})})},k=({colDefs:t,data:o})=>{const r=Object.keys(t),c=Object.keys(o),[l,d]=s.useState(r[0]||""),[n,m]=s.useState(c[0]||""),[a,u]=s.useState("a"),f=s.useMemo(()=>(console.log("memo call to createDataSourceWrapper"),S(o[n],2e3)),[n]),b={activeCol:a};return e.jsxs("div",{style:{height:500,width:800},children:[e.jsx(p,{label:"activeCol",options:["a","b","c"],value:a,onChange:u}),e.jsx(p,{label:"ColDef",options:r,value:l,onChange:d}),e.jsx(p,{label:"Data",options:c,value:n,onChange:m}),e.jsx(j,{colDefs:t[l],data:o[n],datasource:f,extra_context:b})]})},P={title:"ConceptExamples/AGGrid",component:k,parameters:{layout:"centered"},tags:["autodocs"]},T=[{field:"a",headerName:"a",cellDataType:!1},{field:"b",headerName:"b",cellDataType:!1},{field:"c",headerName:"c",cellDataType:!1}],F=[{field:"a",headerName:"a",cellDataType:!1},{field:"a",headerName:"a"},{field:"b",headerName:"b"}],i={args:{colDefs:{colormapconfig:T,IntFloatConfig:F},data:{simple:[{a:50,b:5,c:8},{a:70,b:10,c:3},{a:300,b:3,c:42},{a:200,b:19,c:20}],double:[{a:50,b:5,c:8},{a:70,b:10,c:3},{a:300,b:3,c:42},{a:200,b:19,c:20},{a:50,b:5,c:8},{a:70,b:10,c:3},{a:300,b:3,c:42},{a:200,b:19,c:20}]}}};var D,h,C;i.parameters={...i.parameters,docs:{...(D=i.parameters)==null?void 0:D.docs,source:{originalSource:`{
  args: {
    colDefs: {
      colormapconfig: config1,
      IntFloatConfig: config2
    },
    data: {
      simple: [{
        a: 50,
        b: 5,
        c: 8
      }, {
        a: 70,
        b: 10,
        c: 3
      }, {
        a: 300,
        b: 3,
        c: 42
      }, {
        a: 200,
        b: 19,
        c: 20
      }],
      double: [{
        a: 50,
        b: 5,
        c: 8
      }, {
        a: 70,
        b: 10,
        c: 3
      }, {
        a: 300,
        b: 3,
        c: 42
      }, {
        a: 200,
        b: 19,
        c: 20
      }, {
        a: 50,
        b: 5,
        c: 8
      }, {
        a: 70,
        b: 10,
        c: 3
      }, {
        a: 300,
        b: 3,
        c: 42
      }, {
        a: 200,
        b: 19,
        c: 20
      }]
    }
  }
}`,...(C=(h=i.parameters)==null?void 0:h.docs)==null?void 0:C.source}}};const W=["Default"];export{i as Default,W as __namedExportsOrder,P as default};
