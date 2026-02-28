import{j as n}from"./jsx-runtime-DiklIkkE.js";import{a as Sa}from"./gridUtils-DsHN3qVl.js";import{S as ka,a as Ia}from"./StoryUtils-B9xKXyRO.js";import{d as ga,H as d,a as ma,N as ba,c as Da}from"./DFViewerDataHelper-l27HaZum.js";import{r as l}from"./index-DRjF_FHU.js";import"./lodash-CGIzQN7T.js";import"./HistogramCell-CrXfgV_n.js";import"./index-Bx0Ph3cE.js";import"./ChartCell-ClfxlV_N.js";import"./tiny-invariant-CopsF_GD.js";import"./main.esm-B8BDqAWP.js";import"./client-DQginrwT.js";const r=a=>({col_name:a,header_name:a,displayer_args:{displayer:"obj"}}),s=(a,e,i)=>({col_name:a,header_name:a,displayer_args:{displayer:"float",min_fraction_digits:e,max_fraction_digits:i}}),k=(a,e,i)=>({col_name:a,header_name:a,displayer_args:{displayer:"integer",min_digits:e,max_digits:i}}),Fa={col_name:"index",header_name:"index",displayer_args:{displayer:"string"}},za=({data:a,df_viewer_config:e,secondary_df_viewer_config:i,summary_stats_data:w,outside_df_params:j})=>n.jsx(ka,{children:n.jsx(Ea,{data:a,df_viewer_config:e,secondary_df_viewer_config:i,summary_stats_data:w,outside_df_params:j})}),Ea=({data:a,df_viewer_config:e,secondary_df_viewer_config:i,summary_stats_data:w,outside_df_params:j})=>{const[C,ya]=l.useState(!1),[S,xa]=l.useState(!1),[D,ua]=l.useState("none"),F={none:void 0,"500ms":500,"1.5 s":1500,"5s":5e3},ha=Da(a,F[D]),va=C&&i||e,wa=S?"some error":void 0,[ja,Ca]=l.useState(["b","b_header"]);return n.jsxs("div",{style:{height:500,width:800},children:[n.jsxs("div",{style:{marginBottom:"10px",display:"flex",alignItems:"center",gap:"10px"},children:[n.jsx("button",{onClick:()=>ya(!C),children:"Toggle Config"}),n.jsx(Ia,{label:"dsDelay",options:Object.keys(F),value:D,onChange:ua}),n.jsxs("span",{children:["Current Config: ",C?"Secondary":"Primary"]}),n.jsx("button",{onClick:()=>xa(!S),children:"Toggle Error"}),n.jsxs("span",{children:["Error State: ",S?"Error":"No Error"]})]}),n.jsx(Sa,{data_wrapper:ha,df_viewer_config:va,summary_stats_data:w,activeCol:ja,setActiveCol:Ca,outside_df_params:j,error_info:wa})]})},Za={title:"Buckaroo/DFViewer/DFViewerInfiniteShadow",component:za,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},Ma=[{a:20,b:"foo"},{a:30,b:"bar"},{a:NaN,b:NaN},{a:null,b:null},{a:void 0,b:void 0}],_=[Fa],La={column_config:[s("a",2,8),k("a",2,3),r("b"),{col_name:"b",header_name:"b",displayer_args:{displayer:"string"}}],pinned_rows:[],left_col_configs:_},Na={column_config:[s("a",2,8),k("a",2,3),r("b")],pinned_rows:[],left_col_configs:_},I={column_config:[r("a"),r("b"),r("c"),r("d")],pinned_rows:[{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],left_col_configs:_},o={column_config:[s("a",2,8),k("a",2,3),r("b")],pinned_rows:[{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],left_col_configs:[]},c={args:{data:Ma,df_viewer_config:La,secondary_df_viewer_config:o}},z=5e3,t={args:{data:ga({a:ba(z,3,50),b:ma(z)}),df_viewer_config:Na,secondary_df_viewer_config:I}},p={args:{data:[],df_viewer_config:I,secondary_df_viewer_config:o,summary_stats_data:d}},Pa={column_config:[{col_name:"a",header_name:"a",displayer_args:{displayer:"obj"},color_map_config:{color_rule:"color_map",map_name:"BLUE_TO_YELLOW",val_column:"b"}},{col_name:"b",header_name:"b",displayer_args:{displayer:"obj"},color_map_config:{color_rule:"color_map",map_name:"BLUE_TO_YELLOW",val_column:"c"}},s("c",1,4),s("d",1,4)],pinned_rows:[{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],left_col_configs:_},f={args:{data:[{a:50,b:5,c:8},{a:70,b:10,c:3},{a:300,b:3,c:42},{a:200,b:19,c:20}],df_viewer_config:Pa,secondary_df_viewer_config:o,summary_stats_data:d}},qa={column_config:[{col_path:["super","sub_a2"],field:"a",displayer_args:{displayer:"obj"}},{col_name:"a",col_path:["super","sub_a"],field:"a",displayer_args:{displayer:"obj"}},{col_path:["super","sub_a2"],field:"a",displayer_args:{displayer:"obj"}},{col_path:["super","sub_c"],field:"c",displayer_args:{displayer:"obj"}},{col_name:"b",col_path:["super 2","b"],field:"b",displayer_args:{displayer:"obj"}}],pinned_rows:[],left_col_configs:_},Oa={column_config:[{col_path:["super","foo","a"],field:"a",displayer_args:{displayer:"obj"}},{col_name:"a",col_path:["super","foo","b"],field:"a",displayer_args:{displayer:"obj"}},{col_path:["super","bar","a"],field:"a",displayer_args:{displayer:"obj"}},{col_path:["super","bar","b"],field:"c",displayer_args:{displayer:"obj"}},{col_name:"b",col_path:["super 2","b"],field:"b",displayer_args:{displayer:"obj"}}],pinned_rows:[],left_col_configs:_},g={args:{data:[{a:50,b:5,c:"asdfasdf"},{a:70,b:10,c:"foo bar ba"},{a:300,b:3,c:"stop breaking down"},{a:200,b:19,c:"exile on main"}],df_viewer_config:qa,secondary_df_viewer_config:o,summary_stats_data:d}},m={args:{data:[{a:50,b:5,c:"asdfasdf"},{a:70,b:10,c:"foo bar ba"},{a:300,b:3,c:"stop breaking down"},{a:200,b:19,c:"exile on main"}],df_viewer_config:Oa,secondary_df_viewer_config:o,summary_stats_data:d}},Va={pinned_rows:[{primary_key_val:"dtype",displayer_args:{displayer:"obj"}},{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],column_config:[{displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},col_name:"a",header_name:"foo_col"},{tooltip_config:{tooltip_type:"simple",val_column:"b"},displayer_args:{displayer:"obj"},col_name:"b",header_name:"bar_col"}],left_col_configs:[{col_path:[""],field:"index_a",displayer_args:{displayer:"obj"}},{col_path:[""],field:"index_b",displayer_args:{displayer:"obj"}}],extra_grid_config:{},component_config:{}},b={args:{data:[{a:50,b:5,c:"asdfasdf"},{a:70,b:10,c:"foo bar ba"},{a:300,b:3,c:"stop breaking down"},{a:200,b:19,c:"exile on main"}],df_viewer_config:Va,secondary_df_viewer_config:o,summary_stats_data:d}},E=300,y={args:{data:ga({a:ba(E,3,50),b:ma(E)}),df_viewer_config:o,secondary_df_viewer_config:I}},Ra=[{col_name:"index_a",header_name:"index_name_1",displayer_args:{displayer:"obj"},ag_grid_specs:{}},{col_name:"index_a",header_name:"index_name_2",displayer_args:{displayer:"obj"},ag_grid_specs:{headerClass:["last-index-header-class"],cellClass:["last-index-cell-class"]}}],x={args:{data:[{index:0,a:10,b:"foo",index_a:"foo",index_b:"a"},{index:1,a:20,b:"bar",index_a:"foo",index_b:"b"},{index:2,a:30,b:"baz",index_a:"bar",index_b:"a"},{index:3,a:40,b:"quux",index_a:"bar",index_b:"b"},{index:4,a:50,b:"boff",index_a:"bar",index_b:"c"},{index:5,a:60,b:null,index_a:"baz",index_b:"a"}],df_viewer_config:{pinned_rows:[{primary_key_val:"dtype",displayer_args:{displayer:"obj"}},{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],column_config:[{displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},col_name:"a",header_name:"foo_col"},{tooltip_config:{tooltip_type:"simple",val_column:"b"},displayer_args:{displayer:"obj"},col_name:"b",header_name:"bar_col"}],left_col_configs:Ra,extra_grid_config:{},component_config:{}},secondary_df_viewer_config:{pinned_rows:[],column_config:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]},summary_stats_data:[]}},u={args:{data:[{index:0,a:10,b:"foo",index_a:"foo",index_b:"a"},{index:1,a:20,b:"bar",index_a:"foo",index_b:"b"},{index:2,a:30,b:"baz",index_a:"bar",index_b:"a"},{index:3,a:40,b:"quux",index_a:"bar",index_b:"b"},{index:4,a:50,b:"boff",index_a:"bar",index_b:"c"},{index:5,a:60,b:null,index_a:"baz",index_b:"a"}],df_viewer_config:{pinned_rows:[{primary_key_val:"dtype",displayer_args:{displayer:"obj"}},{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],column_config:[{displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},col_name:"a",header_name:"foo_col"},{tooltip_config:{tooltip_type:"simple",val_column:"b"},displayer_args:{displayer:"obj"},col_name:"b",header_name:"bar_col"}],left_col_configs:[{header_name:"",col_name:"index_a",displayer_args:{displayer:"obj"}},{header_name:"",col_name:"index_b",displayer_args:{displayer:"obj"},ag_grid_specs:{headerClass:["last-index-header-class"],cellClass:["last-index-cell-class"]}}],extra_grid_config:{},component_config:{}},secondary_df_viewer_config:{pinned_rows:[],column_config:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]},summary_stats_data:[]}},h={args:{data:[{index:0,a:10,b:20,c:30,d:40,e:50,f:60,index_a:"foo",index_b:"a"},{index:1,a:"foo",b:"bar",c:"baz",d:"quux",e:"boff",f:null,index_a:"foo",index_b:"b"},{index:2,a:10,b:20,c:30,d:40,e:50,f:60,index_a:"bar",index_b:"a"},{index:3,a:"foo",b:"bar",c:"baz",d:"quux",e:"boff",f:null,index_a:"bar",index_b:"b"},{index:4,a:10,b:20,c:30,d:40,e:50,f:60,index_a:"bar",index_b:"c"},{index:5,a:"foo",b:"bar",c:"baz",d:"quux",e:"boff",f:null,index_a:"baz",index_b:"a"}],df_viewer_config:{pinned_rows:[{primary_key_val:"dtype",displayer_args:{displayer:"obj"}},{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],column_config:[{tooltip_config:{tooltip_type:"simple",val_column:"a"},displayer_args:{displayer:"obj"},col_path:["foo","a"],field:"a"},{tooltip_config:{tooltip_type:"simple",val_column:"b"},displayer_args:{displayer:"obj"},col_path:["foo","b"],field:"b"},{tooltip_config:{tooltip_type:"simple",val_column:"c"},displayer_args:{displayer:"obj"},col_path:["bar","a"],field:"c"},{tooltip_config:{tooltip_type:"simple",val_column:"d"},displayer_args:{displayer:"obj"},col_path:["bar","b"],field:"d"},{tooltip_config:{tooltip_type:"simple",val_column:"e"},displayer_args:{displayer:"obj"},col_path:["bar","c"],field:"e"},{displayer_args:{displayer:"float",min_fraction_digits:3,max_fraction_digits:3},col_path:["baz","a"],field:"f"}],left_col_configs:[{col_path:["",""],field:"index_a",displayer_args:{displayer:"obj"}},{col_path:["level_a","level_b"],field:"index_b",displayer_args:{displayer:"obj"},ag_grid_specs:{headerClass:["last-index-header-class"],cellClass:["last-index-cell-class"]}}],extra_grid_config:{},component_config:{}},secondary_df_viewer_config:{pinned_rows:[],column_config:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]},summary_stats_data:[]}},v={args:{data:[{index:0,a:10,b:"foo",index_a:"foo",index_b:"a",index_c:3},{index:1,a:20,b:"bar",index_a:"foo",index_b:"b",index_c:2},{index:2,a:30,b:"baz",index_a:"bar",index_b:"a",index_c:1},{index:3,a:40,b:"quux",index_a:"bar",index_b:"b",index_c:3},{index:4,a:50,b:"boff",index_a:"bar",index_b:"c",index_c:5},{index:5,a:60,b:null,index_a:"baz",index_b:"a",index_c:6}],df_viewer_config:{pinned_rows:[{primary_key_val:"dtype",displayer_args:{displayer:"obj"}},{primary_key_val:"histogram",displayer_args:{displayer:"histogram"}}],column_config:[{displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},col_name:"a",header_name:"foo_col"},{tooltip_config:{tooltip_type:"simple",val_column:"b"},displayer_args:{displayer:"obj"},col_name:"b",header_name:"bar_col"},{displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},col_name:"a",header_name:"foo_col"},{displayer_args:{displayer:"obj"},col_name:"b",header_name:"bar_col"},{displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},col_name:"a",header_name:"foo_col"},{displayer_args:{displayer:"obj"},col_name:"b",header_name:"bar_col"},{displayer_args:{displayer:"float",min_fraction_digits:0,max_fraction_digits:0},col_name:"a",header_name:"foo_col"},{displayer_args:{displayer:"obj"},col_name:"b",header_name:"bar_col"}],left_col_configs:[{header_name:"",col_name:"index_a",displayer_args:{displayer:"obj"},ag_grid_specs:{pinned:"left"}},{header_name:"",col_name:"index_b",displayer_args:{displayer:"obj"},ag_grid_specs:{pinned:"left"}},{header_name:"",col_name:"index_c",displayer_args:{displayer:"obj"},ag_grid_specs:{pinned:"left"}}],extra_grid_config:{},component_config:{}},secondary_df_viewer_config:{pinned_rows:[],column_config:[],left_col_configs:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}}]},summary_stats_data:[]}};var M,L,N;c.parameters={...c.parameters,docs:{...(M=c.parameters)==null?void 0:M.docs,source:{originalSource:`{
  args: {
    //@ts-ignore
    // the undefineds aren't allowed in the type but do happen in the wild
    data: data,
    df_viewer_config: primaryConfigPrimary,
    secondary_df_viewer_config: IntFloatConfig
  }
}`,...(N=(L=c.parameters)==null?void 0:L.docs)==null?void 0:N.source}}};var P,q,O;t.parameters={...t.parameters,docs:{...(P=t.parameters)==null?void 0:P.docs,source:{originalSource:`{
  args: {
    data: dictOfArraystoDFData({
      'a': NRandom(N, 3, 50),
      'b': arange(N)
    }),
    df_viewer_config: LargeConfig,
    secondary_df_viewer_config: PinnedRowConfig
  }
}`,...(O=(q=t.parameters)==null?void 0:q.docs)==null?void 0:O.source}}};var V,R,H;p.parameters={...p.parameters,docs:{...(V=p.parameters)==null?void 0:V.docs,source:{originalSource:`{
  args: {
    data: [],
    df_viewer_config: PinnedRowConfig,
    secondary_df_viewer_config: IntFloatConfig,
    summary_stats_data: HistogramSummaryStats
  }
}`,...(H=(R=p.parameters)==null?void 0:R.docs)==null?void 0:H.source}}};var T,U,W;f.parameters={...f.parameters,docs:{...(T=f.parameters)==null?void 0:T.docs,source:{originalSource:`{
  args: {
    data: [{
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
    df_viewer_config: ColorMapDFViewerConfig,
    secondary_df_viewer_config: IntFloatConfig,
    summary_stats_data: HistogramSummaryStats
  }
}`,...(W=(U=f.parameters)==null?void 0:U.docs)==null?void 0:W.source}}};var B,A,Y;g.parameters={...g.parameters,docs:{...(B=g.parameters)==null?void 0:B.docs,source:{originalSource:`{
  args: {
    data: [{
      a: 50,
      b: 5,
      c: "asdfasdf"
    }, {
      a: 70,
      b: 10,
      c: "foo bar ba"
    }, {
      a: 300,
      b: 3,
      c: "stop breaking down"
    }, {
      a: 200,
      b: 19,
      c: "exile on main"
    }],
    df_viewer_config: MultiIndexDFViewerConfig,
    secondary_df_viewer_config: IntFloatConfig,
    summary_stats_data: HistogramSummaryStats
  }
}`,...(Y=(A=g.parameters)==null?void 0:A.docs)==null?void 0:Y.source}}};var G,X,J;m.parameters={...m.parameters,docs:{...(G=m.parameters)==null?void 0:G.docs,source:{originalSource:`{
  args: {
    data: [{
      a: 50,
      b: 5,
      c: "asdfasdf"
    }, {
      a: 70,
      b: 10,
      c: "foo bar ba"
    }, {
      a: 300,
      b: 3,
      c: "stop breaking down"
    }, {
      a: 200,
      b: 19,
      c: "exile on main"
    }],
    df_viewer_config: ThreeLevelIndex,
    secondary_df_viewer_config: IntFloatConfig,
    summary_stats_data: HistogramSummaryStats
  }
}`,...(J=(X=m.parameters)==null?void 0:X.docs)==null?void 0:J.source}}};var K,Q,Z;b.parameters={...b.parameters,docs:{...(K=b.parameters)==null?void 0:K.docs,source:{originalSource:`{
  args: {
    data: [{
      a: 50,
      b: 5,
      c: "asdfasdf"
    }, {
      a: 70,
      b: 10,
      c: "foo bar ba"
    }, {
      a: 300,
      b: 3,
      c: "stop breaking down"
    }, {
      a: 200,
      b: 19,
      c: "exile on main"
    }],
    df_viewer_config: FIP,
    secondary_df_viewer_config: IntFloatConfig,
    summary_stats_data: HistogramSummaryStats
  }
}`,...(Z=(Q=b.parameters)==null?void 0:Q.docs)==null?void 0:Z.source}}};var $,aa,na;y.parameters={...y.parameters,docs:{...($=y.parameters)==null?void 0:$.docs,source:{originalSource:`{
  args: {
    data: dictOfArraystoDFData({
      'a': NRandom(MEDIUM, 3, 50),
      'b': arange(MEDIUM)
    }),
    df_viewer_config: IntFloatConfig,
    secondary_df_viewer_config: PinnedRowConfig
  }
}`,...(na=(aa=y.parameters)==null?void 0:aa.docs)==null?void 0:na.source}}};var ea,ia,ra;x.parameters={...x.parameters,docs:{...(ea=x.parameters)==null?void 0:ea.docs,source:{originalSource:`{
  "args": {
    "data": [{
      "index": 0,
      "a": 10,
      "b": "foo",
      "index_a": "foo",
      "index_b": "a"
    }, {
      "index": 1,
      "a": 20,
      "b": "bar",
      "index_a": "foo",
      "index_b": "b"
    }, {
      "index": 2,
      "a": 30,
      "b": "baz",
      "index_a": "bar",
      "index_b": "a"
    }, {
      "index": 3,
      "a": 40,
      "b": "quux",
      "index_a": "bar",
      "index_b": "b"
    }, {
      "index": 4,
      "a": 50,
      "b": "boff",
      "index_a": "bar",
      "index_b": "c"
    }, {
      "index": 5,
      "a": 60,
      "b": null,
      "index_a": "baz",
      "index_b": "a"
    }],
    "df_viewer_config": {
      "pinned_rows": [{
        "primary_key_val": "dtype",
        "displayer_args": {
          "displayer": "obj"
        }
      }, {
        "primary_key_val": "histogram",
        "displayer_args": {
          "displayer": "histogram"
        }
      }],
      "column_config": [{
        "displayer_args": {
          "displayer": "float",
          "min_fraction_digits": 0,
          "max_fraction_digits": 0
        },
        "col_name": "a",
        "header_name": "foo_col"
      }, {
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "b"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_name": "b",
        "header_name": "bar_col"
      }],
      left_col_configs: left_col_configs2,
      "extra_grid_config": {},
      "component_config": {}
    },
    "secondary_df_viewer_config": {
      "pinned_rows": [],
      "column_config": [],
      "left_col_configs": [{
        "col_name": "index",
        "header_name": "index",
        "displayer_args": {
          "displayer": "obj"
        }
      }]
    },
    "summary_stats_data": []
  }
}`,...(ra=(ia=x.parameters)==null?void 0:ia.docs)==null?void 0:ra.source}}};var oa,_a,sa;u.parameters={...u.parameters,docs:{...(oa=u.parameters)==null?void 0:oa.docs,source:{originalSource:`{
  "args": {
    "data": [{
      "index": 0,
      "a": 10,
      "b": "foo",
      "index_a": "foo",
      "index_b": "a"
    }, {
      "index": 1,
      "a": 20,
      "b": "bar",
      "index_a": "foo",
      "index_b": "b"
    }, {
      "index": 2,
      "a": 30,
      "b": "baz",
      "index_a": "bar",
      "index_b": "a"
    }, {
      "index": 3,
      "a": 40,
      "b": "quux",
      "index_a": "bar",
      "index_b": "b"
    }, {
      "index": 4,
      "a": 50,
      "b": "boff",
      "index_a": "bar",
      "index_b": "c"
    }, {
      "index": 5,
      "a": 60,
      "b": null,
      "index_a": "baz",
      "index_b": "a"
    }],
    "df_viewer_config": {
      "pinned_rows": [{
        "primary_key_val": "dtype",
        "displayer_args": {
          "displayer": "obj"
        }
      }, {
        "primary_key_val": "histogram",
        "displayer_args": {
          "displayer": "histogram"
        }
      }],
      "column_config": [{
        "displayer_args": {
          "displayer": "float",
          "min_fraction_digits": 0,
          "max_fraction_digits": 0
        },
        "col_name": "a",
        "header_name": "foo_col"
      }, {
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "b"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_name": "b",
        "header_name": "bar_col"
      }],
      "left_col_configs": [{
        header_name: "",
        "col_name": "index_a",
        "displayer_args": {
          "displayer": "obj"
        }
      }, {
        header_name: "",
        "col_name": "index_b",
        "displayer_args": {
          "displayer": "obj"
        },
        "ag_grid_specs": {
          "headerClass": ["last-index-header-class"],
          "cellClass": ["last-index-cell-class"]
        }
      }],
      "extra_grid_config": {},
      "component_config": {}
    },
    "secondary_df_viewer_config": {
      "pinned_rows": [],
      "column_config": [],
      "left_col_configs": [{
        "col_name": "index",
        "header_name": "index",
        "displayer_args": {
          "displayer": "obj"
        }
      }]
    },
    "summary_stats_data": []
  }
}`,...(sa=(_a=u.parameters)==null?void 0:_a.docs)==null?void 0:sa.source}}};var da,la,ca;h.parameters={...h.parameters,docs:{...(da=h.parameters)==null?void 0:da.docs,source:{originalSource:`{
  "args": {
    "data": [{
      "index": 0,
      "a": 10,
      "b": 20,
      "c": 30,
      "d": 40,
      "e": 50,
      "f": 60.0,
      "index_a": "foo",
      "index_b": "a"
    }, {
      "index": 1,
      "a": "foo",
      "b": "bar",
      "c": "baz",
      "d": "quux",
      "e": "boff",
      "f": null,
      "index_a": "foo",
      "index_b": "b"
    }, {
      "index": 2,
      "a": 10,
      "b": 20,
      "c": 30,
      "d": 40,
      "e": 50,
      "f": 60.0,
      "index_a": "bar",
      "index_b": "a"
    }, {
      "index": 3,
      "a": "foo",
      "b": "bar",
      "c": "baz",
      "d": "quux",
      "e": "boff",
      "f": null,
      "index_a": "bar",
      "index_b": "b"
    }, {
      "index": 4,
      "a": 10,
      "b": 20,
      "c": 30,
      "d": 40,
      "e": 50,
      "f": 60.0,
      "index_a": "bar",
      "index_b": "c"
    }, {
      "index": 5,
      "a": "foo",
      "b": "bar",
      "c": "baz",
      "d": "quux",
      "e": "boff",
      "f": null,
      "index_a": "baz",
      "index_b": "a"
    }],
    "df_viewer_config": {
      "pinned_rows": [{
        "primary_key_val": "dtype",
        "displayer_args": {
          "displayer": "obj"
        }
      }, {
        "primary_key_val": "histogram",
        "displayer_args": {
          "displayer": "histogram"
        }
      }],
      "column_config": [{
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "a"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_path": ["foo", "a"],
        "field": "a"
      }, {
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "b"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_path": ["foo", "b"],
        "field": "b"
      }, {
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "c"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_path": ["bar", "a"],
        "field": "c"
      }, {
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "d"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_path": ["bar", "b"],
        "field": "d"
      }, {
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "e"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_path": ["bar", "c"],
        "field": "e"
      }, {
        "displayer_args": {
          "displayer": "float",
          "min_fraction_digits": 3,
          "max_fraction_digits": 3
        },
        "col_path": ["baz", "a"],
        "field": "f"
      }],
      "left_col_configs": [{
        "col_path": ["", ""],
        "field": "index_a",
        "displayer_args": {
          "displayer": "obj"
        }
      }, {
        "col_path": ["level_a", "level_b"],
        "field": "index_b",
        "displayer_args": {
          "displayer": "obj"
        },
        "ag_grid_specs": {
          "headerClass": ["last-index-header-class"],
          "cellClass": ["last-index-cell-class"]
        }
      }],
      "extra_grid_config": {},
      "component_config": {}
    },
    "secondary_df_viewer_config": {
      "pinned_rows": [],
      "column_config": [],
      "left_col_configs": [{
        "col_name": "index",
        "header_name": "index",
        "displayer_args": {
          "displayer": "obj"
        }
      }]
    },
    "summary_stats_data": []
  }
}`,...(ca=(la=h.parameters)==null?void 0:la.docs)==null?void 0:ca.source}}};var ta,pa,fa;v.parameters={...v.parameters,docs:{...(ta=v.parameters)==null?void 0:ta.docs,source:{originalSource:`{
  "args": {
    "data": [{
      "index": 0,
      "a": 10,
      "b": "foo",
      "index_a": "foo",
      "index_b": "a",
      "index_c": 3
    }, {
      "index": 1,
      "a": 20,
      "b": "bar",
      "index_a": "foo",
      "index_b": "b",
      "index_c": 2
    }, {
      "index": 2,
      "a": 30,
      "b": "baz",
      "index_a": "bar",
      "index_b": "a",
      "index_c": 1
    }, {
      "index": 3,
      "a": 40,
      "b": "quux",
      "index_a": "bar",
      "index_b": "b",
      "index_c": 3
    }, {
      "index": 4,
      "a": 50,
      "b": "boff",
      "index_a": "bar",
      "index_b": "c",
      "index_c": 5
    }, {
      "index": 5,
      "a": 60,
      "b": null,
      "index_a": "baz",
      "index_b": "a",
      "index_c": 6
    }],
    "df_viewer_config": {
      "pinned_rows": [{
        "primary_key_val": "dtype",
        "displayer_args": {
          "displayer": "obj"
        }
      }, {
        "primary_key_val": "histogram",
        "displayer_args": {
          "displayer": "histogram"
        }
      }],
      "column_config": [{
        "displayer_args": {
          "displayer": "float",
          "min_fraction_digits": 0,
          "max_fraction_digits": 0
        },
        "col_name": "a",
        "header_name": "foo_col"
      }, {
        "tooltip_config": {
          "tooltip_type": "simple",
          "val_column": "b"
        },
        "displayer_args": {
          "displayer": "obj"
        },
        "col_name": "b",
        "header_name": "bar_col"
      }, {
        "displayer_args": {
          "displayer": "float",
          "min_fraction_digits": 0,
          "max_fraction_digits": 0
        },
        "col_name": "a",
        "header_name": "foo_col"
      }, {
        "displayer_args": {
          "displayer": "obj"
        },
        "col_name": "b",
        "header_name": "bar_col"
      }, {
        "displayer_args": {
          "displayer": "float",
          "min_fraction_digits": 0,
          "max_fraction_digits": 0
        },
        "col_name": "a",
        "header_name": "foo_col"
      }, {
        "displayer_args": {
          "displayer": "obj"
        },
        "col_name": "b",
        "header_name": "bar_col"
      }, {
        "displayer_args": {
          "displayer": "float",
          "min_fraction_digits": 0,
          "max_fraction_digits": 0
        },
        "col_name": "a",
        "header_name": "foo_col"
      }, {
        "displayer_args": {
          "displayer": "obj"
        },
        "col_name": "b",
        "header_name": "bar_col"
      }],
      "left_col_configs": [{
        "header_name": "",
        "col_name": "index_a",
        "displayer_args": {
          "displayer": "obj"
        },
        "ag_grid_specs": {
          pinned: 'left'
        }
      }, {
        "header_name": "",
        "col_name": "index_b",
        "displayer_args": {
          "displayer": "obj"
        },
        "ag_grid_specs": {
          pinned: 'left'
        }
      }, {
        "header_name": "",
        "col_name": "index_c",
        "displayer_args": {
          "displayer": "obj"
        },
        "ag_grid_specs": {
          pinned: 'left'
        }
      }],
      "extra_grid_config": {},
      "component_config": {}
    },
    "secondary_df_viewer_config": {
      "pinned_rows": [],
      "column_config": [],
      "left_col_configs": [{
        "col_name": "index",
        "header_name": "index",
        "displayer_args": {
          "displayer": "obj"
        }
      }]
    },
    "summary_stats_data": []
  }
}`,...(fa=(pa=v.parameters)==null?void 0:pa.docs)==null?void 0:fa.source}}};const $a=["Primary","Large","PinnedRows","ColorMapExample","MultiIndex","ThreeLevelColumnIndex","FailingInMarimo","MedDFVHeight","get_multiindex_with_names_index_df","get_multiindex_index_df","get_multiindex_index_multiindex_with_names_cols_df","get_multiindex3_index_df"];export{f as ColorMapExample,b as FailingInMarimo,t as Large,y as MedDFVHeight,g as MultiIndex,p as PinnedRows,c as Primary,m as ThreeLevelColumnIndex,$a as __namedExportsOrder,Za as default,v as get_multiindex3_index_df,u as get_multiindex_index_df,h as get_multiindex_index_multiindex_with_names_cols_df,x as get_multiindex_with_names_index_df};
