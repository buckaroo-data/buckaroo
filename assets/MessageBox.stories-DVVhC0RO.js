import{j as c}from"./jsx-runtime-DiklIkkE.js";import{r as p}from"./index-DRjF_FHU.js";import{a as Q}from"./gridUtils-ttv7OPgW.js";/* empty css                */import"./lodash-CGIzQN7T.js";import"./HistogramCell-WXbqT_Ov.js";import"./index-Bx0Ph3cE.js";import"./ChartCell-CdGzSEf4.js";import"./tiny-invariant-CopsF_GD.js";import"./main.esm-CraDeAap.js";function M({messages:t}){const[e,i]=p.useState(0),r=p.useRef(0),m=p.useMemo(()=>{if(!t||t.length===0)return r.current!==0&&(r.current=0,i(s=>s+1)),[];const a=t.map((s,n)=>!s||typeof s!="object"?{index:n,time:"",type:"",message:String(s||"")}:{index:n,time:s.time||"",type:s.type||"",message:s.message||"",...Object.fromEntries(Object.entries(s).filter(([u])=>!["time","type","message"].includes(u)))});return t.length!==r.current&&(r.current=t.length,i(s=>s+1)),a},[t]),S=p.useMemo(()=>{if(!t||t.length===0)return{pinned_rows:[],column_config:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]};const a=new Set;t.forEach(n=>{n&&typeof n=="object"&&Object.keys(n).forEach(u=>a.add(u))}),a.add("index"),a.add("time"),a.add("type"),a.add("message");const s=Array.from(a).map(n=>({col_name:n,header_name:n,displayer_args:{displayer:"obj"}}));return{pinned_rows:[],column_config:s,left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]}},[t]),o=()=>{};return!t||t.length===0?null:c.jsx("div",{style:{height:"300px",width:"100%",border:"1px solid red",marginTop:"10px",backgroundColor:"#1a1a1a"},children:c.jsx(Q,{data_wrapper:{data_type:"Raw",data:m,length:m.length},df_viewer_config:S,summary_stats_data:[],activeCol:["",""],setActiveCol:o,error_info:""},`df-viewer-${e}-${m.length}`)})}M.__docgenInfo={description:"",methods:[],displayName:"MessageBox",props:{messages:{required:!0,tsType:{name:"Array",elements:[{name:"signature",type:"object",raw:`{
    time?: string;
    type?: string;
    message?: string;
    [key: string]: any;
}`,signature:{properties:[{key:"time",value:{name:"string",required:!1}},{key:"type",value:{name:"string",required:!1}},{key:"message",value:{name:"string",required:!1}},{key:{name:"string"},value:{name:"any",required:!0}}]}}],raw:`Array<{
    time?: string;
    type?: string;
    message?: string;
    [key: string]: any;
}>`},description:""}}};const ce={title:"Buckaroo/MessageBox",component:M,parameters:{layout:"padded"},tags:["autodocs"],argTypes:{messages:{control:"object",description:"Array of message objects to display"}}},V=[{time:"2024-01-15T10:00:00.000Z",type:"cache",message:"file found in cache with file name /path/to/data.parquet"},{time:"2024-01-15T10:00:01.000Z",type:"cache",message:"file not found in cache for file name /path/to/new_data.parquet"}],H=[{time:"2024-01-15T10:00:02.000Z",type:"cache_info",message:"Cache info. 30 columns in cache, 14 stats per column, total cache size 3.2 kilobytes"}],J=[{time:"2024-01-15T10:00:03.000Z",type:"execution",message:"Execution update: started",time_start:"2024-01-15T10:00:03.000Z",pid:12345,status:"started",num_columns:5,num_expressions:12,explicit_column_list:["col1","col2","col3","col4","col5"]},{time:"2024-01-15T10:00:05.500Z",type:"execution",message:"Execution update: finished",time_start:"2024-01-15T10:00:03.000Z",pid:12345,status:"finished",num_columns:5,num_expressions:12,explicit_column_list:["col1","col2","col3","col4","col5"],execution_time_secs:2.5},{time:"2024-01-15T10:00:08.000Z",type:"execution",message:"Execution update: error",time_start:"2024-01-15T10:00:08.000Z",pid:12346,status:"error",num_columns:2,num_expressions:8,explicit_column_list:["col6","col7"]}],W=[...V,...H,...J],g={args:{messages:[]}},l={args:{messages:V}},d={args:{messages:H}},_={args:{messages:J}},h={args:{messages:W}},f={args:{messages:Array.from({length:50},(t,e)=>({time:`2024-01-15T10:00:${String(e).padStart(2,"0")}.000Z`,type:e%3===0?"cache":e%3===1?"cache_info":"execution",message:`Message ${e+1}: ${e%3===0?"Cache operation":e%3===1?"Cache info update":"Execution update"}`,...e%3===2?{time_start:`2024-01-15T10:00:${String(e).padStart(2,"0")}.000Z`,pid:12345+e,status:e%5===0?"error":"finished",num_columns:e%10+1,num_expressions:e%20+5,explicit_column_list:Array.from({length:e%10+1},(i,r)=>`col${r+1}`),execution_time_secs:e%10*.5}:{}}))}},x={args:{messages:[{time:"2024-01-15T10:00:00.000Z",type:"cache",message:"file found in cache with file name /very/long/path/to/a/very/large/dataset/with/many/subdirectories/data.parquet"},{time:"2024-01-15T10:00:01.000Z",type:"execution",message:"Execution update: finished",time_start:"2024-01-15T10:00:00.000Z",pid:12345,status:"finished",num_columns:150,num_expressions:300,explicit_column_list:Array.from({length:150},(t,e)=>`very_long_column_name_${e}_with_many_characters`),execution_time_secs:123.456}]}},y={render:t=>{const[e,i]=p.useState([]),[r,m]=p.useState(!1),S=()=>{m(!0),i([]),setTimeout(()=>{i(s=>[...s,{time:new Date().toISOString(),type:"cache",message:"file not found in cache for file name /path/to/data.parquet"}])},500),setTimeout(()=>{i(s=>[...s,{time:new Date().toISOString(),type:"cache_info",message:"Cache info. 30 columns in cache, 14 stats per column, total cache size 3.2 kilobytes"}])},1e3);let o=0;const a=()=>{o++;const s=Array.from({length:3},(u,P)=>`col${o*3+P}`),n=o%3===0?"error":o%2===0?"finished":"started";i(u=>[...u,{time:new Date().toISOString(),type:"execution",message:`Execution update: ${n}`,time_start:new Date().toISOString(),pid:12345+o,status:n,num_columns:s.length,num_expressions:12,explicit_column_list:s,...n==="finished"?{execution_time_secs:1.5+Math.random()}:{}}]),o<10?setTimeout(a,1500):m(!1)};setTimeout(a,2e3)};return c.jsxs("div",{children:[c.jsxs("div",{style:{marginBottom:"10px"},children:[c.jsx("button",{onClick:S,disabled:r,style:{padding:"8px 16px",marginRight:"10px"},children:r?"Streaming...":"Start Streaming Messages"}),e.length>0&&c.jsxs("span",{style:{marginLeft:"10px"},children:[e.length," message",e.length!==1?"s":""]})]}),c.jsx(M,{messages:e})]})},args:{messages:[]}};var T,v,w;g.parameters={...g.parameters,docs:{...(T=g.parameters)==null?void 0:T.docs,source:{originalSource:`{
  args: {
    messages: []
  }
}`,...(w=(v=g.parameters)==null?void 0:v.docs)==null?void 0:w.source}}};var C,b,E;l.parameters={...l.parameters,docs:{...(C=l.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    messages: cacheMessages
  }
}`,...(E=(b=l.parameters)==null?void 0:b.docs)==null?void 0:E.source}}};var j,Z,I;d.parameters={...d.parameters,docs:{...(j=d.parameters)==null?void 0:j.docs,source:{originalSource:`{
  args: {
    messages: cacheInfoMessages
  }
}`,...(I=(Z=d.parameters)==null?void 0:Z.docs)==null?void 0:I.source}}};var $,k,A;_.parameters={..._.parameters,docs:{...($=_.parameters)==null?void 0:$.docs,source:{originalSource:`{
  args: {
    messages: executionMessages
  }
}`,...(A=(k=_.parameters)==null?void 0:k.docs)==null?void 0:A.source}}};var O,q,D;h.parameters={...h.parameters,docs:{...(O=h.parameters)==null?void 0:O.docs,source:{originalSource:`{
  args: {
    messages: mixedMessages
  }
}`,...(D=(q=h.parameters)==null?void 0:q.docs)==null?void 0:D.source}}};var B,U,R;f.parameters={...f.parameters,docs:{...(B=f.parameters)==null?void 0:B.docs,source:{originalSource:`{
  args: {
    messages: Array.from({
      length: 50
    }, (_, i) => ({
      time: \`2024-01-15T10:00:\${String(i).padStart(2, "0")}.000Z\`,
      type: i % 3 === 0 ? "cache" : i % 3 === 1 ? "cache_info" : "execution",
      message: \`Message \${i + 1}: \${i % 3 === 0 ? "Cache operation" : i % 3 === 1 ? "Cache info update" : "Execution update"}\`,
      ...(i % 3 === 2 ? {
        time_start: \`2024-01-15T10:00:\${String(i).padStart(2, "0")}.000Z\`,
        pid: 12345 + i,
        status: i % 5 === 0 ? "error" : "finished",
        num_columns: i % 10 + 1,
        num_expressions: i % 20 + 5,
        explicit_column_list: Array.from({
          length: i % 10 + 1
        }, (_, j) => \`col\${j + 1}\`),
        execution_time_secs: i % 10 * 0.5
      } : {})
    }))
  }
}`,...(R=(U=f.parameters)==null?void 0:U.docs)==null?void 0:R.source}}};var G,L,z;x.parameters={...x.parameters,docs:{...(G=x.parameters)==null?void 0:G.docs,source:{originalSource:`{
  args: {
    messages: [{
      time: "2024-01-15T10:00:00.000Z",
      type: "cache",
      message: "file found in cache with file name /very/long/path/to/a/very/large/dataset/with/many/subdirectories/data.parquet"
    }, {
      time: "2024-01-15T10:00:01.000Z",
      type: "execution",
      message: "Execution update: finished",
      time_start: "2024-01-15T10:00:00.000Z",
      pid: 12345,
      status: "finished",
      num_columns: 150,
      num_expressions: 300,
      explicit_column_list: Array.from({
        length: 150
      }, (_, i) => \`very_long_column_name_\${i}_with_many_characters\`),
      execution_time_secs: 123.456
    }]
  }
}`,...(z=(L=x.parameters)==null?void 0:L.docs)==null?void 0:z.source}}};var K,F,N;y.parameters={...y.parameters,docs:{...(K=y.parameters)==null?void 0:K.docs,source:{originalSource:`{
  render: args => {
    const [messages, setMessages] = useState<typeof args.messages>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const startStreaming = () => {
      setIsStreaming(true);
      setMessages([]);

      // Simulate cache messages
      setTimeout(() => {
        setMessages(prev => [...prev, {
          time: new Date().toISOString(),
          type: "cache",
          message: "file not found in cache for file name /path/to/data.parquet"
        }]);
      }, 500);
      setTimeout(() => {
        setMessages(prev => [...prev, {
          time: new Date().toISOString(),
          type: "cache_info",
          message: "Cache info. 30 columns in cache, 14 stats per column, total cache size 3.2 kilobytes"
        }]);
      }, 1000);

      // Simulate execution updates
      let execCount = 0;
      const addExecutionUpdate = () => {
        execCount++;
        const colGroup = Array.from({
          length: 3
        }, (_, i) => \`col\${execCount * 3 + i}\`);
        const status = execCount % 3 === 0 ? "error" : execCount % 2 === 0 ? "finished" : "started";
        setMessages(prev => [...prev, {
          time: new Date().toISOString(),
          type: "execution",
          message: \`Execution update: \${status}\`,
          time_start: new Date().toISOString(),
          pid: 12345 + execCount,
          status: status,
          num_columns: colGroup.length,
          num_expressions: 12,
          explicit_column_list: colGroup,
          ...(status === "finished" ? {
            execution_time_secs: 1.5 + Math.random()
          } : {})
        }]);
        if (execCount < 10) {
          setTimeout(addExecutionUpdate, 1500);
        } else {
          setIsStreaming(false);
        }
      };
      setTimeout(addExecutionUpdate, 2000);
    };
    return <div>
        <div style={{
        marginBottom: "10px"
      }}>
          <button onClick={startStreaming} disabled={isStreaming} style={{
          padding: "8px 16px",
          marginRight: "10px"
        }}>
            {isStreaming ? "Streaming..." : "Start Streaming Messages"}
          </button>
          {messages.length > 0 && <span style={{
          marginLeft: "10px"
        }}>
              {messages.length} message{messages.length !== 1 ? "s" : ""}
            </span>}
        </div>
        <MessageBox messages={messages} />
      </div>;
  },
  args: {
    messages: []
  }
}`,...(N=(F=y.parameters)==null?void 0:F.docs)==null?void 0:N.source}}};const me=["Empty","CacheMessages","CacheInfo","ExecutionUpdates","MixedMessages","ManyMessages","LongMessages","StreamingMessages"];export{d as CacheInfo,l as CacheMessages,g as Empty,_ as ExecutionUpdates,x as LongMessages,f as ManyMessages,h as MixedMessages,y as StreamingMessages,me as __namedExportsOrder,ce as default};
