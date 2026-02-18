import{j as v}from"./jsx-runtime-DiklIkkE.js";import{R as n}from"./index-DRjF_FHU.js";import{g as M,O as _}from"./OperationsList-CPVzoTey.js";import{s as E,d as A,m as W}from"./OperationExamples-Doz6Ao4n.js";const b=({operations:j})=>{const[t,K]=n.useState(j),[L,R]=n.useState(M(t,1));return v.jsx(_,{operations:t,setOperations:K,activeKey:L,setActiveKey:R})},z={title:"Components/OperationsList",component:b,parameters:{layout:"centered"},tags:["autodocs"]},a={args:{operations:E}},e={args:{operations:[]}},s={args:{operations:[E[0]]}},r={args:{operations:A}},o={args:{operations:W}};var p,i,c;a.parameters={...a.parameters,docs:{...(p=a.parameters)==null?void 0:p.docs,source:{originalSource:`{
  args: {
    operations: sampleOperations
  }
}`,...(c=(i=a.parameters)==null?void 0:i.docs)==null?void 0:c.source}}};var m,g,u;e.parameters={...e.parameters,docs:{...(m=e.parameters)==null?void 0:m.docs,source:{originalSource:`{
  args: {
    operations: []
  }
}`,...(u=(g=e.parameters)==null?void 0:g.docs)==null?void 0:u.source}}};var d,l,O;s.parameters={...s.parameters,docs:{...(d=s.parameters)==null?void 0:d.docs,source:{originalSource:`{
  args: {
    operations: [sampleOperations[0]]
  }
}`,...(O=(l=s.parameters)==null?void 0:l.docs)==null?void 0:O.source}}};var y,S,f;r.parameters={...r.parameters,docs:{...(y=r.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    operations: dataCleaningOps
  }
}`,...(f=(S=r.parameters)==null?void 0:S.docs)==null?void 0:f.source}}};var x,C,D;o.parameters={...o.parameters,docs:{...(x=o.parameters)==null?void 0:x.docs,source:{originalSource:`{
  args: {
    operations: manyOperations
  }
}`,...(D=(C=o.parameters)==null?void 0:C.docs)==null?void 0:D.source}}};const B=["Default","Empty","SingleOperation","DataCleaning","ManyOperations"];export{r as DataCleaning,a as Default,e as Empty,o as ManyOperations,s as SingleOperation,B as __namedExportsOrder,z as default};
