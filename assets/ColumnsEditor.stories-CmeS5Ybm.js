import{j as r}from"./jsx-runtime-DiklIkkE.js";import{r as a}from"./index-DRjF_FHU.js";import{C as n}from"./ColumnsEditor-C6hCUTDk.js";/* empty css                */import{s as h,b as t,d as D,m as L}from"./OperationExamples-Doz6Ao4n.js";import"./Operations-Xk-4uWct.js";import"./lodash-CGIzQN7T.js";import"./OperationsList-CPVzoTey.js";import"./gridUtils-Bm544I_D.js";import"./HistogramCell-CrXfgV_n.js";import"./index-Bx0Ph3cE.js";import"./ChartCell-ClfxlV_N.js";import"./tiny-invariant-CopsF_GD.js";import"./main.esm-B8BDqAWP.js";const B={col_name:"index",header_name:"index",displayer_args:{displayer:"string"}},R=[B],s={column_config:[{col_name:"index",header_name:"index",displayer_args:{displayer:"integer",min_digits:3,max_digits:5}},{col_name:"svg_column",header_name:"svg_column",displayer_args:{displayer:"SVGDisplayer"}},{col_name:"link_column",header_name:"link_column",displayer_args:{displayer:"linkify"}},{col_name:"nanObject",header_name:"nanObject",displayer_args:{displayer:"integer",min_digits:3,max_digits:5},color_map_config:{color_rule:"color_map",map_name:"BLUE_TO_YELLOW",val_column:"tripduration"}}],extra_grid_config:{rowHeight:105},component_config:{height_fraction:1},pinned_rows:[],left_col_configs:R},i={transformed_df:{dfviewer_config:{pinned_rows:[],column_config:[],left_col_configs:R},data:[]},generated_py_code:"default py code",transform_error:void 0},A={title:"Buckaroo/ColumnsEditor",component:n,parameters:{layout:"centered"},tags:["autodocs"]},p={render:()=>{const[e,o]=a.useState(h);return r.jsx(n,{df_viewer_config:s,activeColumn:["b","index"],operation_result:i,command_config:t,operations:e,setOperations:o})}},m={render:()=>{const[e,o]=a.useState([]);return r.jsx(n,{df_viewer_config:s,activeColumn:["a","index"],operation_result:i,command_config:t,operations:e,setOperations:o})}},c={render:()=>{const[e,o]=a.useState([h[0]]);return r.jsx(n,{df_viewer_config:s,activeColumn:["a","index"],operation_result:i,command_config:t,operations:e,setOperations:o})}},d={render:()=>{const[e,o]=a.useState(D);return r.jsx(n,{df_viewer_config:s,activeColumn:["a","index"],operation_result:i,command_config:t,operations:e,setOperations:o})}},_={render:()=>{const[e,o]=a.useState(L);return r.jsx(n,{df_viewer_config:s,activeColumn:["a","index"],operation_result:i,command_config:t,operations:e,setOperations:o})}};var l,u,g;p.parameters={...p.parameters,docs:{...(l=p.parameters)==null?void 0:l.docs,source:{originalSource:`{
  render: () => {
    const [operations, setOperations] = useState<Operation[]>(sampleOperations);
    return <ColumnsEditor df_viewer_config={df_viewer_config} activeColumn={["b", "index"]} operation_result={baseOperationResults} command_config={bakedCommandConfig} operations={operations} setOperations={setOperations} />;
  }
}`,...(g=(u=p.parameters)==null?void 0:u.docs)==null?void 0:g.source}}};var f,O,C;m.parameters={...m.parameters,docs:{...(f=m.parameters)==null?void 0:f.docs,source:{originalSource:`{
  render: () => {
    const [operations, setOperations] = useState<Operation[]>([]);
    return <ColumnsEditor df_viewer_config={df_viewer_config} activeColumn={["a", "index"]} operation_result={baseOperationResults} command_config={bakedCommandConfig} operations={operations} setOperations={setOperations} />;
  }
}`,...(C=(O=m.parameters)==null?void 0:O.docs)==null?void 0:C.source}}};var x,v,y;c.parameters={...c.parameters,docs:{...(x=c.parameters)==null?void 0:x.docs,source:{originalSource:`{
  render: () => {
    const [operations, setOperations] = useState<Operation[]>([sampleOperations[0]]);
    return <ColumnsEditor df_viewer_config={df_viewer_config} activeColumn={["a", "index"]} operation_result={baseOperationResults} command_config={bakedCommandConfig} operations={operations} setOperations={setOperations} />;
  }
}`,...(y=(v=c.parameters)==null?void 0:v.docs)==null?void 0:y.source}}};var S,b,w;d.parameters={...d.parameters,docs:{...(S=d.parameters)==null?void 0:S.docs,source:{originalSource:`{
  render: () => {
    const [operations, setOperations] = useState<Operation[]>(dataCleaningOps);
    return <ColumnsEditor df_viewer_config={df_viewer_config} activeColumn={["a", "index"]} operation_result={baseOperationResults} command_config={bakedCommandConfig} operations={operations} setOperations={setOperations} />;
  }
}`,...(w=(b=d.parameters)==null?void 0:b.docs)==null?void 0:w.source}}};var E,k,j;_.parameters={..._.parameters,docs:{...(E=_.parameters)==null?void 0:E.docs,source:{originalSource:`{
  render: () => {
    const [operations, setOperations] = useState<Operation[]>(manyOperations);
    return <ColumnsEditor df_viewer_config={df_viewer_config} activeColumn={["a", "index"]} operation_result={baseOperationResults} command_config={bakedCommandConfig} operations={operations} setOperations={setOperations} />;
  }
}`,...(j=(k=_.parameters)==null?void 0:k.docs)==null?void 0:j.source}}};const J=["Default","Empty","SingleOperation","DataCleaning","ManyOperations"];export{d as DataCleaning,p as Default,m as Empty,_ as ManyOperations,c as SingleOperation,J as __namedExportsOrder,A as default};
