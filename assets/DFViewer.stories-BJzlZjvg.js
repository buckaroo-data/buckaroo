import{j as i}from"./jsx-runtime-DiklIkkE.js";import{r as s}from"./index-DRjF_FHU.js";/* empty css                */import{D as F}from"./gridUtils-Bgxku6QU.js";import"./index.esm-Bddaha_j.js";import"./_baseEach-B-y44WsN.js";import"./isArray-Dxzbedgu.js";import"./index-DIvcuAjW.js";import"./HistogramCell-Bzivjlh2.js";import"./ChartCell-BfPIzAg-.js";import"./tiny-invariant-CopsF_GD.js";import"./isString-CNnovG4X.js";const D=({df_data:v,df_viewer_config:N,summary_stats_data:w,activeCol:d,setActiveCol:t})=>{if(t===void 0){let[j,C]=s.useState(["b","b"])}if(d===void 0){let[j,C]=s.useState(["b","b"])}return i.jsx("div",{style:{height:500,width:800},children:i.jsx(F,{df_data:v,df_viewer_config:N,summary_stats_data:w,activeCol:d,setActiveCol:t})})},L={title:"Buckaroo/DFViewer/DFViewer",component:D,parameters:{layout:"centered"},tags:["autodocs"],argTypes:{}},S={col_name:"index",header_name:"index",displayer_args:{displayer:"string"}},o=[S],e={args:{df_data:[{a:20,b:"foo"},{a:30,b:"bar"}],df_viewer_config:{column_config:[{col_name:"a",header_name:"a1",displayer_args:{displayer:"float",min_fraction_digits:2,max_fraction_digits:8}},{col_name:"a",header_name:"a2",displayer_args:{displayer:"integer",min_digits:2,max_digits:3}},{col_name:"b",header_name:"b",displayer_args:{displayer:"obj"}}],pinned_rows:[],left_col_configs:o}}},a={args:{df_data:[{index:0,date:"06/11/2021",date2:"06/11/2021",tt:"foo"},{index:1,date:"Nov, 22nd 2021",date2:"22/11/2021",tt:"bar"},{index:2,date:"24th of November, 2021",date2:"24/11/2021",tt:"baz"},{index:3,date:"24th of November, 2021",date2:"24/11/2021"},{index:4,date:"24th of November, 2021",date2:"24/11/2021",tt:9999},{index:5,date:"24th of November, 2021",date2:"24/11/2021",tt:"baz"}],df_viewer_config:{column_config:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}},{col_name:"date",header_name:"date",displayer_args:{displayer:"string"},tooltip_config:{tooltip_type:"simple",val_column:"tt"}},{col_name:"date2",header_name:"date2",displayer_args:{displayer:"string"}}],pinned_rows:[],left_col_configs:o}}},n={args:{df_data:[{index:0,date:"06/11/2021",color:"red"},{index:1,date:"Nov, 22nd 2021",color:"#f8f8a1"},{index:2,date:"24th of November, 2021",color:"teal"},{index:3,date:"24th of November, 2021",color:"#aaa"},{index:4,date:"24th of November, 2021"},{index:5,date:"24th of November, 2021"}],df_viewer_config:{column_config:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}},{col_name:"date",header_name:"date",displayer_args:{displayer:"string"},color_map_config:{color_rule:"color_from_column",val_column:"color"}}],pinned_rows:[],left_col_configs:o}}},R=[{lineRed:33,name:"2000-01-01 00:00:00"},{lineRed:33,name:"2001-01-01 00:00:00"},{lineRed:66,name:"unique"},{lineRed:100,name:"end"}],r={args:{df_data:[{index:0,chart1:R}],df_viewer_config:{column_config:[{col_name:"index",header_name:"index",displayer_args:{displayer:"obj"}},{col_name:"chart1",header_name:"chart1",displayer_args:{displayer:"chart"}}],pinned_rows:[],left_col_configs:o}}};var _,l,c;e.parameters={...e.parameters,docs:{...(_=e.parameters)==null?void 0:_.docs,source:{originalSource:`{
  args: {
    df_data: [{
      'a': 20,
      'b': "foo"
    }, {
      'a': 30,
      'b': "bar"
    }],
    df_viewer_config: {
      column_config: [{
        col_name: 'a',
        header_name: 'a1',
        displayer_args: {
          displayer: 'float',
          min_fraction_digits: 2,
          max_fraction_digits: 8
        }
        //tooltip_config: { tooltip_type: 'summary_series' },
      }, {
        col_name: 'a',
        header_name: 'a2',
        displayer_args: {
          displayer: 'integer',
          min_digits: 2,
          max_digits: 3
        }
      }, {
        col_name: 'b',
        header_name: 'b',
        displayer_args: {
          displayer: 'obj'
        }
      }],
      pinned_rows: [],
      left_col_configs
    }
  }
}`,...(c=(l=e.parameters)==null?void 0:l.docs)==null?void 0:c.source}}};var m,p,f;a.parameters={...a.parameters,docs:{...(m=a.parameters)==null?void 0:m.docs,source:{originalSource:`{
  args: {
    df_data: [{
      index: 0,
      date: '06/11/2021',
      date2: '06/11/2021',
      tt: 'foo'
    }, {
      index: 1,
      date: 'Nov, 22nd 2021',
      date2: '22/11/2021',
      tt: 'bar'
    }, {
      index: 2,
      date: '24th of November, 2021',
      date2: '24/11/2021',
      tt: 'baz'
    }, {
      index: 3,
      date: '24th of November, 2021',
      date2: '24/11/2021'
    }, {
      index: 4,
      date: '24th of November, 2021',
      date2: '24/11/2021',
      tt: 9999
    }, {
      index: 5,
      date: '24th of November, 2021',
      date2: '24/11/2021',
      tt: 'baz'
    }],
    df_viewer_config: {
      column_config: [{
        col_name: 'index',
        header_name: 'index',
        displayer_args: {
          'displayer': 'obj'
        }
      }, {
        col_name: 'date',
        header_name: 'date',
        displayer_args: {
          'displayer': 'string'
        },
        tooltip_config: {
          'tooltip_type': 'simple',
          'val_column': 'tt'
        }
      }, {
        col_name: 'date2',
        header_name: 'date2',
        displayer_args: {
          'displayer': 'string'
        }
      }],
      pinned_rows: [],
      left_col_configs
    }
  }
}`,...(f=(p=a.parameters)==null?void 0:p.docs)==null?void 0:f.source}}};var g,h,x;n.parameters={...n.parameters,docs:{...(g=n.parameters)==null?void 0:g.docs,source:{originalSource:`{
  args: {
    df_data: [{
      index: 0,
      date: '06/11/2021',
      color: "red"
    }, {
      index: 1,
      date: 'Nov, 22nd 2021',
      color: "#f8f8a1"
    }, {
      index: 2,
      date: '24th of November, 2021',
      color: "teal"
    }, {
      index: 3,
      date: '24th of November, 2021',
      color: "#aaa"
    }, {
      index: 4,
      date: '24th of November, 2021'
    }, {
      index: 5,
      date: '24th of November, 2021'
    }],
    df_viewer_config: {
      column_config: [{
        col_name: 'index',
        header_name: 'index',
        displayer_args: {
          'displayer': 'obj'
        }
      }, {
        col_name: 'date',
        header_name: 'date',
        displayer_args: {
          'displayer': 'string'
        },
        color_map_config: {
          color_rule: "color_from_column",
          val_column: "color"
        }
      }],
      pinned_rows: [],
      left_col_configs
    }
  }
}`,...(x=(h=n.parameters)==null?void 0:h.docs)==null?void 0:x.source}}};var y,b,u;r.parameters={...r.parameters,docs:{...(y=r.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    df_data: [{
      index: 0,
      chart1: lineChart
    }],
    df_viewer_config: {
      column_config: [{
        col_name: 'index',
        header_name: 'index',
        displayer_args: {
          'displayer': 'obj'
        }
      }, {
        col_name: 'chart1',
        header_name: 'chart1',
        displayer_args: {
          'displayer': 'chart'
        }
      }],
      pinned_rows: [],
      left_col_configs
    }
  }
}`,...(u=(b=r.parameters)==null?void 0:b.docs)==null?void 0:u.source}}};const W=["Primary","Tooltip","ColorFromCol","Chart"];export{r as Chart,n as ColorFromCol,e as Primary,a as Tooltip,W as __namedExportsOrder,L as default};
