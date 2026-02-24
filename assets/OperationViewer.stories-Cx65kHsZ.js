import{j}from"./jsx-runtime-DiklIkkE.js";import{R as w}from"./index-DRjF_FHU.js";import{O as R}from"./Operations-Xk-4uWct.js";import{b as o,s as z,d as V,m as M}from"./OperationExamples-Doz6Ao4n.js";/* empty css                */import"./lodash-CGIzQN7T.js";import"./OperationsList-CPVzoTey.js";const h=({operations:y,activeColumn:S,allColumns:k,command_config:x})=>{const[D,E]=w.useState(y);return j.jsx(R,{operations:D,setOperations:E,activeColumn:S,allColumns:k,command_config:x})},H={title:"Buckaroo/Chrome/OperationViewer-in-stories-dir",component:h,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},a={args:{operations:z,activeColumn:"foo-column",allColumns:["foo-col","bar-col","baz-col"],command_config:o}},n={args:{operations:[],activeColumn:"foo-column",allColumns:["foo-col","bar-col","baz-col"],command_config:o}},e={args:{operations:[z[0]],activeColumn:"foo-column",allColumns:["foo-col","bar-col","baz-col"],command_config:o}},r={args:{operations:V,activeColumn:"foo-column",allColumns:["foo-col","bar-col","baz-col"],command_config:o}},s={args:{operations:M,activeColumn:"foo-column",allColumns:["foo-col","bar-col","baz-col"],command_config:o}};var c,m,l;a.parameters={...a.parameters,docs:{...(c=a.parameters)==null?void 0:c.docs,source:{originalSource:`{
  args: {
    operations: sampleOperations,
    activeColumn: 'foo-column',
    allColumns: ['foo-col', 'bar-col', 'baz-col'],
    command_config: bakedCommandConfig
  }
}`,...(l=(m=a.parameters)==null?void 0:m.docs)==null?void 0:l.source}}};var t,i,p;n.parameters={...n.parameters,docs:{...(t=n.parameters)==null?void 0:t.docs,source:{originalSource:`{
  args: {
    operations: [],
    activeColumn: 'foo-column',
    allColumns: ['foo-col', 'bar-col', 'baz-col'],
    command_config: bakedCommandConfig
  }
}`,...(p=(i=n.parameters)==null?void 0:i.docs)==null?void 0:p.source}}};var u,d,f;e.parameters={...e.parameters,docs:{...(u=e.parameters)==null?void 0:u.docs,source:{originalSource:`{
  args: {
    operations: [sampleOperations[0]],
    activeColumn: 'foo-column',
    allColumns: ['foo-col', 'bar-col', 'baz-col'],
    command_config: bakedCommandConfig
  }
}`,...(f=(d=e.parameters)==null?void 0:d.docs)==null?void 0:f.source}}};var g,C,b;r.parameters={...r.parameters,docs:{...(g=r.parameters)==null?void 0:g.docs,source:{originalSource:`{
  args: {
    operations: dataCleaningOps,
    activeColumn: 'foo-column',
    allColumns: ['foo-col', 'bar-col', 'baz-col'],
    command_config: bakedCommandConfig
  }
}`,...(b=(C=r.parameters)==null?void 0:C.docs)==null?void 0:b.source}}};var O,_,v;s.parameters={...s.parameters,docs:{...(O=s.parameters)==null?void 0:O.docs,source:{originalSource:`{
  args: {
    operations: manyOperations,
    activeColumn: 'foo-column',
    allColumns: ['foo-col', 'bar-col', 'baz-col'],
    command_config: bakedCommandConfig
  }
}`,...(v=(_=s.parameters)==null?void 0:_.docs)==null?void 0:v.source}}};const I=["Default","Empty","SingleOperation","DataCleaning","ManyOperations"];export{r as DataCleaning,a as Default,n as Empty,s as ManyOperations,e as SingleOperation,I as __namedExportsOrder,H as default};
