import{j as l}from"./jsx-runtime-DiklIkkE.js";import{r as i}from"./index-DRjF_FHU.js";import{a as y}from"./gridUtils-BHKvpUsw.js";function f({messages:t}){const[p,d]=i.useState(0),a=i.useRef(0),o=i.useMemo(()=>{if(!t||t.length===0)return a.current!==0&&(a.current=0,d(e=>e+1)),[];const n=t.map((e,r)=>!e||typeof e!="object"?{index:r,time:"",type:"",message:String(e||"")}:{index:r,time:e.time||"",type:e.type||"",message:e.message||"",...Object.fromEntries(Object.entries(e).filter(([s])=>!["time","type","message"].includes(s)))});return t.length!==a.current&&(a.current=t.length,d(e=>e+1)),n},[t]),c=i.useMemo(()=>{if(!t||t.length===0)return{pinned_rows:[],column_config:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]};const n=new Set;t.forEach(r=>{r&&typeof r=="object"&&Object.keys(r).forEach(s=>n.add(s))}),n.add("index"),n.add("time"),n.add("type"),n.add("message");const e=Array.from(n).map(r=>({col_name:r,header_name:r,displayer_args:{displayer:"obj"}}));return{pinned_rows:[],column_config:e,left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]}},[t]),u=()=>{};return!t||t.length===0?null:l.jsx("div",{style:{height:"300px",width:"100%",border:"1px solid red",marginTop:"10px",backgroundColor:"#1a1a1a"},children:l.jsx(y,{data_wrapper:{data_type:"Raw",data:o,length:o.length},df_viewer_config:c,summary_stats_data:[],activeCol:["",""],setActiveCol:u,error_info:""},`df-viewer-${p}-${o.length}`)})}f.__docgenInfo={description:"",methods:[],displayName:"MessageBox",props:{messages:{required:!0,tsType:{name:"Array",elements:[{name:"signature",type:"object",raw:`{
    time?: string;
    type?: string;
    message?: string;
    [key: string]: any;
}`,signature:{properties:[{key:"time",value:{name:"string",required:!1}},{key:"type",value:{name:"string",required:!1}},{key:"message",value:{name:"string",required:!1}},{key:{name:"string"},value:{name:"any",required:!0}}]}}],raw:`Array<{
    time?: string;
    type?: string;
    message?: string;
    [key: string]: any;
}>`},description:""}}};export{f as M};
