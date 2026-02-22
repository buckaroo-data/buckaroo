import{j as a}from"./jsx-runtime-DiklIkkE.js";import{r as S}from"./index-DRjF_FHU.js";import{M as H}from"./MessageBox-D8GKbDe0.js";/* empty css                */import"./gridUtils-BcXT2XPm.js";import"./lodash-CGIzQN7T.js";import"./HistogramCell-DJbyo4_Z.js";import"./index-Bx0Ph3cE.js";import"./ChartCell-ClfxlV_N.js";import"./tiny-invariant-CopsF_GD.js";import"./main.esm-B8BDqAWP.js";const ce={title:"Buckaroo/MessageBox",component:H,parameters:{layout:"padded"},tags:["autodocs"],argTypes:{messages:{control:"object",description:"Array of message objects to display"}}},J=[{time:"2024-01-15T10:00:00.000Z",type:"cache",message:"file found in cache with file name /path/to/data.parquet"},{time:"2024-01-15T10:00:01.000Z",type:"cache",message:"file not found in cache for file name /path/to/new_data.parquet"}],K=[{time:"2024-01-15T10:00:02.000Z",type:"cache_info",message:"Cache info. 30 columns in cache, 14 stats per column, total cache size 3.2 kilobytes"}],N=[{time:"2024-01-15T10:00:03.000Z",type:"execution",message:"Execution update: started",time_start:"2024-01-15T10:00:03.000Z",pid:12345,status:"started",num_columns:5,num_expressions:12,explicit_column_list:["col1","col2","col3","col4","col5"]},{time:"2024-01-15T10:00:05.500Z",type:"execution",message:"Execution update: finished",time_start:"2024-01-15T10:00:03.000Z",pid:12345,status:"finished",num_columns:5,num_expressions:12,explicit_column_list:["col1","col2","col3","col4","col5"],execution_time_secs:2.5},{time:"2024-01-15T10:00:08.000Z",type:"execution",message:"Execution update: error",time_start:"2024-01-15T10:00:08.000Z",pid:12346,status:"error",num_columns:2,num_expressions:8,explicit_column_list:["col6","col7"]}],V=[...J,...K,...N],r={args:{messages:[]}},i={args:{messages:J}},c={args:{messages:K}},m={args:{messages:N}},u={args:{messages:V}},g={args:{messages:Array.from({length:50},(h,e)=>({time:`2024-01-15T10:00:${String(e).padStart(2,"0")}.000Z`,type:e%3===0?"cache":e%3===1?"cache_info":"execution",message:`Message ${e+1}: ${e%3===0?"Cache operation":e%3===1?"Cache info update":"Execution update"}`,...e%3===2?{time_start:`2024-01-15T10:00:${String(e).padStart(2,"0")}.000Z`,pid:12345+e,status:e%5===0?"error":"finished",num_columns:e%10+1,num_expressions:e%20+5,explicit_column_list:Array.from({length:e%10+1},(n,o)=>`col${o+1}`),execution_time_secs:e%10*.5}:{}}))}},p={args:{messages:[{time:"2024-01-15T10:00:00.000Z",type:"cache",message:"file found in cache with file name /very/long/path/to/a/very/large/dataset/with/many/subdirectories/data.parquet"},{time:"2024-01-15T10:00:01.000Z",type:"execution",message:"Execution update: finished",time_start:"2024-01-15T10:00:00.000Z",pid:12345,status:"finished",num_columns:150,num_expressions:300,explicit_column_list:Array.from({length:150},(h,e)=>`very_long_column_name_${e}_with_many_characters`),execution_time_secs:123.456}]}},l={render:h=>{const[e,n]=S.useState([]),[o,_]=S.useState(!1),P=()=>{_(!0),n([]),setTimeout(()=>{n(t=>[...t,{time:new Date().toISOString(),type:"cache",message:"file not found in cache for file name /path/to/data.parquet"}])},500),setTimeout(()=>{n(t=>[...t,{time:new Date().toISOString(),type:"cache_info",message:"Cache info. 30 columns in cache, 14 stats per column, total cache size 3.2 kilobytes"}])},1e3);let s=0;const x=()=>{s++;const t=Array.from({length:3},(f,Q)=>`col${s*3+Q}`),d=s%3===0?"error":s%2===0?"finished":"started";n(f=>[...f,{time:new Date().toISOString(),type:"execution",message:`Execution update: ${d}`,time_start:new Date().toISOString(),pid:12345+s,status:d,num_columns:t.length,num_expressions:12,explicit_column_list:t,...d==="finished"?{execution_time_secs:1.5+Math.random()}:{}}]),s<10?setTimeout(x,1500):_(!1)};setTimeout(x,2e3)};return a.jsxs("div",{children:[a.jsxs("div",{style:{marginBottom:"10px"},children:[a.jsx("button",{onClick:P,disabled:o,style:{padding:"8px 16px",marginRight:"10px"},children:o?"Streaming...":"Start Streaming Messages"}),e.length>0&&a.jsxs("span",{style:{marginLeft:"10px"},children:[e.length," message",e.length!==1?"s":""]})]}),a.jsx(H,{messages:e})]})},args:{messages:[]}};var y,M,T;r.parameters={...r.parameters,docs:{...(y=r.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    messages: []
  }
}`,...(T=(M=r.parameters)==null?void 0:M.docs)==null?void 0:T.source}}};var C,E,Z;i.parameters={...i.parameters,docs:{...(C=i.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    messages: cacheMessages
  }
}`,...(Z=(E=i.parameters)==null?void 0:E.docs)==null?void 0:Z.source}}};var v,w,I;c.parameters={...c.parameters,docs:{...(v=c.parameters)==null?void 0:v.docs,source:{originalSource:`{
  args: {
    messages: cacheInfoMessages
  }
}`,...(I=(w=c.parameters)==null?void 0:w.docs)==null?void 0:I.source}}};var $,b,j;m.parameters={...m.parameters,docs:{...($=m.parameters)==null?void 0:$.docs,source:{originalSource:`{
  args: {
    messages: executionMessages
  }
}`,...(j=(b=m.parameters)==null?void 0:b.docs)==null?void 0:j.source}}};var A,O,D;u.parameters={...u.parameters,docs:{...(A=u.parameters)==null?void 0:A.docs,source:{originalSource:`{
  args: {
    messages: mixedMessages
  }
}`,...(D=(O=u.parameters)==null?void 0:O.docs)==null?void 0:D.source}}};var k,q,B;g.parameters={...g.parameters,docs:{...(k=g.parameters)==null?void 0:k.docs,source:{originalSource:`{
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
}`,...(B=(q=g.parameters)==null?void 0:q.docs)==null?void 0:B.source}}};var U,G,L;p.parameters={...p.parameters,docs:{...(U=p.parameters)==null?void 0:U.docs,source:{originalSource:`{
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
}`,...(L=(G=p.parameters)==null?void 0:G.docs)==null?void 0:L.source}}};var z,R,F;l.parameters={...l.parameters,docs:{...(z=l.parameters)==null?void 0:z.docs,source:{originalSource:`{
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
}`,...(F=(R=l.parameters)==null?void 0:R.docs)==null?void 0:F.source}}};const me=["Empty","CacheMessages","CacheInfo","ExecutionUpdates","MixedMessages","ManyMessages","LongMessages","StreamingMessages"];export{c as CacheInfo,i as CacheMessages,r as Empty,m as ExecutionUpdates,p as LongMessages,g as ManyMessages,u as MixedMessages,l as StreamingMessages,me as __namedExportsOrder,ce as default};
