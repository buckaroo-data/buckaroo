import type { Meta, StoryObj } from "@storybook/react";
import { DFViewerInfinite } from "../components/DFViewerParts/DFViewerInfinite";
import { DFViewerConfig, ColumnConfig, NormalColumnConfig } from "../components/DFViewerParts/DFWhole";

import {SelectBox } from './StoryUtils'
//import { SetColumnFunc } from "../components/DFViewerParts/gridUtils";
import { ShadowDomWrapper } from "./StoryUtils";
import { DatasourceWrapper, createDatasourceWrapper, dictOfArraystoDFData, arange, NRandom, HistogramSummaryStats } from "../components/DFViewerParts/DFViewerDataHelper";
import { useState } from "react";


const objColumn = (col_name: string): ColumnConfig => {
  const foo: NormalColumnConfig = {
    col_name,
    header_name:col_name,
    displayer_args: {
      displayer: 'obj' as const,
    }
  }
  return foo;
};

const floatColumn = (col_name: string, min_fraction_digits: number, max_fraction_digits: number): ColumnConfig => ({
  col_name,
  header_name:col_name,
  displayer_args: {
    displayer: 'float' as const,
    min_fraction_digits,
    max_fraction_digits,
  },
});

const integerColumn = (col_name: string, min_digits: number, max_digits: number): ColumnConfig => ({
  col_name,
  header_name:col_name,
  displayer_args: {
    displayer: 'integer' as const,
    min_digits,
    max_digits,
  },
});

const INDEX_COL_CONFIG:NormalColumnConfig =         {
          col_name: 'index',
	  header_name: 'index',
          displayer_args: {
            displayer: 'string',
          },
        }


const DFViewerInfiniteWrap = ({
  data,
  df_viewer_config,
  secondary_df_viewer_config,
  summary_stats_data,
  outside_df_params,
}: {
  data: any[];
  df_viewer_config: DFViewerConfig;
  secondary_df_viewer_config?: DFViewerConfig;
  summary_stats_data?: any[];
  outside_df_params?: any;
}) => {

  return (<ShadowDomWrapper> 
    <DFViewerInfiniteWrapInner
              data={data}
              df_viewer_config={df_viewer_config}
              secondary_df_viewer_config={secondary_df_viewer_config}
              summary_stats_data={summary_stats_data}
              outside_df_params={outside_df_params}
               />
  </ShadowDomWrapper>);
}
const DFViewerInfiniteWrapInner = ({
    data,
    df_viewer_config,
    secondary_df_viewer_config,
    summary_stats_data,
    outside_df_params,
}: {
    data: any[];
    df_viewer_config: DFViewerConfig;
    secondary_df_viewer_config?: DFViewerConfig;
    summary_stats_data?: any[];
    outside_df_params?: any;
}) => {
  //console.log("error_info", error_info);
  const [useSecondaryConfig, setUseSecondaryConfig] = useState(false);
  const [showError, setShowError] = useState(false);
  const [dsDelay, setDsDelay] = useState("none");

  const dsDelayOptions:Record<string, number|undefined> = {"none":undefined, "500ms": 500, "1.5 s":1_500, "5s":5_000}

  const data_wrapper: DatasourceWrapper = createDatasourceWrapper(data, dsDelayOptions[dsDelay]);
  const activeConfig = useSecondaryConfig ? (secondary_df_viewer_config || df_viewer_config) : df_viewer_config;
  const currentError = showError ? "some error" : undefined;

  const [activeCol, setActiveCol] = useState("b");
  return (
      <div style={{ height: 500, width: 800 }}>
        <div style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={() => setUseSecondaryConfig(!useSecondaryConfig)}
          >
            Toggle Config
          </button>

                        <SelectBox
                        label="dsDelay"
                        options={Object.keys(dsDelayOptions)}
                        value={dsDelay}
                        onChange={setDsDelay}
                      />
          <span>Current Config: {useSecondaryConfig ? 'Secondary' : 'Primary'}</span>
          <button
            onClick={() => setShowError(!showError)}
          >
            Toggle Error
          </button>
          <span>Error State: {showError ? 'Error' : 'No Error'}</span>
        </div>
        <DFViewerInfinite
          data_wrapper={data_wrapper}
          df_viewer_config={activeConfig}
          summary_stats_data={summary_stats_data}
          activeCol={activeCol}
          setActiveCol={setActiveCol}
          outside_df_params={outside_df_params}
          error_info={currentError} />
      </div>)
}


// More on how to set up stories at: https://storybook.js.org/docs/writing-stories#default-export
const meta = {
  title: "Buckaroo/DFViewer/DFViewerInfiniteShadow",
  component: DFViewerInfiniteWrap,
  parameters: {
    // Optional parameter to center the component in the Canvas. More
    // info: https://storybook.js.org/docs/configure/story-layout
    layout: "centered",
      
  },
  // This component will have an automatically generated Autodocs
  // entry: https://storybook.js.org/docs/writing-docs/autodocs
  tags: ["autodocs"],
  // More on argTypes: https://storybook.js.org/docs/api/argtypes
  argTypes: {
      //backgroundColor: { control: "color" },
      //operations: 
  },
  // Use `fn` to spy on the onClick arg, which will appear in the
  // actions panel once invoked:
  // https://storybook.js.org/docs/essentials/actions#action-args
  //args: { onClick: fn() },
} satisfies Meta<typeof DFViewerInfiniteWrap>;

export default meta;
type Story = StoryObj<typeof meta>;
const data = [
    {'a':20, 'b':"foo"},
    {'a':30, 'b':"bar"},
    {'a':NaN, 'b':NaN},
    {'a':null, 'b':null},
    {'a':undefined, 'b':undefined}

  ];
const left_col_configs = [INDEX_COL_CONFIG];
const primaryConfigPrimary:DFViewerConfig = {
      column_config: [
        floatColumn('a', 2, 8),
        integerColumn('a', 2, 3),
        objColumn('b'),
        {
          col_name: 'b',
	  header_name: 'b',
          displayer_args: {
            displayer: 'string',
          },
        },
      ],	
  pinned_rows: [],
  left_col_configs,
  
   };
    const LargeConfig:DFViewerConfig = {
      column_config: [
      floatColumn('a', 2, 8),
      integerColumn('a', 2, 3),
      objColumn('b'),
    ],
      pinned_rows:[],
  left_col_configs,
  }
  const PinnedRowConfig:DFViewerConfig = {
    column_config: [
      objColumn('a'),
      objColumn('b'),
      objColumn('c'),
      objColumn('d'),
    ],
    pinned_rows: [{
      'primary_key_val': 'histogram',
      'displayer_args': { 'displayer': 'histogram' }
    }],
  left_col_configs,
  };
const IntFloatConfig:DFViewerConfig =  {
    column_config: [
    floatColumn('a', 2, 8),
    integerColumn('a', 2, 3),
    objColumn('b'),
  ],
  pinned_rows:[{
    'primary_key_val': 'histogram',
    'displayer_args': { 'displayer': 'histogram' }
  }],
  left_col_configs:[]
  //component_config: {dfvHeight:200}
};

export const Primary: Story = {
  args: {
    //@ts-ignore
    // the undefineds aren't allowed in the type but do happen in the wild
    data: data,
    df_viewer_config: primaryConfigPrimary,
    secondary_df_viewer_config:IntFloatConfig
  },
};

const N = 5_000;

export const Large: Story = {
  args: {
    data: dictOfArraystoDFData({'a':NRandom(N, 3,50), 'b':arange(N)}),
    df_viewer_config: LargeConfig,
    secondary_df_viewer_config: PinnedRowConfig,
    }

}


export const PinnedRows: Story = {
  args: {
    data: [], 
    df_viewer_config: PinnedRowConfig,
    secondary_df_viewer_config: IntFloatConfig,
    summary_stats_data: HistogramSummaryStats
  }
}

const ColorMapDFViewerConfig:DFViewerConfig = {
  column_config: [
    {col_name:'a',
      header_name:'a',
      displayer_args: { displayer:'obj' },
        color_map_config: {
            color_rule: "color_map",
            map_name: "BLUE_TO_YELLOW",
            val_column: "b"
    }},
    {col_name:'b',
      header_name:'b',
      
      displayer_args: { displayer:'obj' },
        color_map_config: {
            color_rule: "color_map",
            map_name: "BLUE_TO_YELLOW",
            val_column: "c"
    }},
    floatColumn('c', 1,4),
    floatColumn('d', 1,4)

  ],
   pinned_rows: [{
    'primary_key_val': 'histogram',
    'displayer_args': { 'displayer': 'histogram' }
   }],
  left_col_configs,
}

export const ColorMapExample: Story = {

  args: {
    data: [
      {a:50,  b:5,   c: 8},
      {a:70,  b:10,  c: 3},
      {a:300, b:3,   c:42},
      {a:200, b:19,  c:20},
    ],
    df_viewer_config: ColorMapDFViewerConfig,
    secondary_df_viewer_config :IntFloatConfig,
    summary_stats_data: HistogramSummaryStats

  }
}



const MultiIndexDFViewerConfig:DFViewerConfig = {
  column_config: [
    { col_path:['super', 'sub_a2'],
      'field': 'a',
      displayer_args: { displayer:'obj' },
    },
    {col_name:'a',
      col_path:['super', 'sub_a'],
      'field': 'a',
      displayer_args: { displayer:'obj' },
    },
    { col_path:['super', 'sub_a2'],
      'field': 'a',
      displayer_args: { displayer:'obj' },
    },
    {col_path:['super', 'sub_c'],
      'field': 'c',
      displayer_args: { displayer:'obj' },
    },
    {col_name:'b',
      col_path:['super 2', 'b'],
      field:'b',
      displayer_args: { displayer:'obj' },
    },
  ],
  pinned_rows: [],
  left_col_configs,
}

const ThreeLevelIndex:DFViewerConfig = {
  column_config: [
    { col_path:['super', 'foo', 'a'],
      'field': 'a',
      displayer_args: { displayer:'obj' },
    },
    {col_name:'a',
      col_path:['super', 'foo', 'b'],
      'field': 'a',
      displayer_args: { displayer:'obj' },
    },
    { col_path:['super', 'bar', 'a'],
      'field': 'a',
      displayer_args: { displayer:'obj' },
    },
    {col_path:['super', 'bar', 'b'],
      'field': 'c',
      displayer_args: { displayer:'obj' },
    },
    {col_name:'b',
      col_path:['super 2', 'b'],
      field:'b',
      displayer_args: { displayer:'obj' },
    },
  ],
  pinned_rows: [],
  left_col_configs,
}

  /*
const examples:ColGroupDef[] = [
  {
    headerName: 'Name & Country',
    children: [
      { field: 'athlete' },
      { field: 'country' }
    ]
  },
  {
    headerName: 'Sports Results',
    children: [
      { columnGroupShow: 'closed', field: 'total' },
      { columnGroupShow: 'open', field: 'gold' },
      { columnGroupShow: 'open', field: 'silver' },
      { columnGroupShow: 'open', field: 'bronze' },
    ],
  }
]
   */

export const MultiIndex: Story = {

  args: {
    data: [
      {a:50,  b:5,   c: "asdfasdf"},
      {a:70,  b:10,  c: "foo bar ba"},
      {a:300, b:3,   c: "stop breaking down"},
      {a:200, b:19,  c: "exile on main"},
    ],
    df_viewer_config: MultiIndexDFViewerConfig,
    secondary_df_viewer_config :IntFloatConfig,
    summary_stats_data: HistogramSummaryStats

  }
}

export const ThreeLevelColumnIndex: Story = {

  args: {
    data: [
      {a:50,  b:5,   c: "asdfasdf"},
      {a:70,  b:10,  c: "foo bar ba"},
      {a:300, b:3,   c: "stop breaking down"},
      {a:200, b:19,  c: "exile on main"},
    ],
    df_viewer_config: ThreeLevelIndex,
    secondary_df_viewer_config :IntFloatConfig,
    summary_stats_data: HistogramSummaryStats

  }
}

const FIP:DFViewerConfig = {
  "pinned_rows": [
    {
      "primary_key_val": "dtype",
      "displayer_args": {
        "displayer": "obj"
      }
    },
    {
      "primary_key_val": "histogram",
      "displayer_args": {
        "displayer": "histogram"
      }
    }
  ],
  "column_config": [
    {
      "displayer_args": {
        "displayer": "float",
        "min_fraction_digits": 0,
        "max_fraction_digits": 0
      },
      "col_name": "a",
      "header_name": "foo_col"
    },
    {
      "tooltip_config": {
        "tooltip_type": "simple",
        "val_column": "b"
      },
      "displayer_args": {
        "displayer": "obj"
      },
      "col_name": "b",
      "header_name": "bar_col"
    }
  ],
  "left_col_configs": [
    {
      "col_path": [
        ""
      ],
      "field": "index_a",
      "displayer_args": {
        "displayer": "obj"
      }
    },
    {
      "col_path": [
        ""
      ],
      "field": "index_b",
      "displayer_args": {
        "displayer": "obj"
      }
    }
  ],
  "extra_grid_config": {},
  "component_config": {}
};



export const FailingInMarimo:Story = {

  args: {
    data: [
      {a:50,  b:5,   c: "asdfasdf"},
      {a:70,  b:10,  c: "foo bar ba"},
      {a:300, b:3,   c: "stop breaking down"},
      {a:200, b:19,  c: "exile on main"},
    ],
    df_viewer_config: FIP,
    
    secondary_df_viewer_config :IntFloatConfig,
    summary_stats_data: HistogramSummaryStats
  }
}

const MEDIUM= 300;

export const MedDFVHeight: Story = {
  args: {
    data:dictOfArraystoDFData({'a':NRandom(MEDIUM, 3,50), 'b':arange(MEDIUM)   }),
    df_viewer_config: IntFloatConfig,
    secondary_df_viewer_config: PinnedRowConfig,
    }
}
// const left_col_configs2:ColumnConfig[] = [
//                 {
//                     "col_path": [
//                         "index_name_1"
//                     ],
//                     "field": "index_a",
//                     "displayer_args": {
//                         "displayer": "obj"
//                     }
//                 },
//                 {
//                     "col_path": [
//                         "index_name_2"
//                     ],
//                     "field": "index_b",
//                     "displayer_args": {
//                         "displayer": "obj"
//                     }
		  
//                 }
//             ]

//const a =  cssProperty: =  "border";

const left_col_configs2:ColumnConfig[] = [
                {
                  "col_name": "index_a",
		  "header_name": "index_name_1",
                    "displayer_args": {
                        "displayer": "obj"
                    },
		  ag_grid_specs: {}
                },
                {
                  "col_name": "index_a",
		  "header_name": "index_name_2",
                    "displayer_args": {
                        "displayer": "obj"
                    },
		  ag_grid_specs: {
		    headerClass: ['last-index-header-class'],
		    cellClass: ['last-index-cell-class'],
		  }
                }
            ]

// // from ddd.get_multiindex_with_names_index_df()
export const get_multiindex_with_names_index_df :Story = {
    "args": {
        "data": [
            {
                "index": 0,
                "a": 10,
                "b": "foo",
                "index_a": "foo",
                "index_b": "a"
            },
            {
                "index": 1,
                "a": 20,
                "b": "bar",
                "index_a": "foo",
                "index_b": "b"
            },
            {
                "index": 2,
                "a": 30,
                "b": "baz",
                "index_a": "bar",
                "index_b": "a"
            },
            {
                "index": 3,
                "a": 40,
                "b": "quux",
                "index_a": "bar",
                "index_b": "b"
            },
            {
                "index": 4,
                "a": 50,
                "b": "boff",
                "index_a": "bar",
                "index_b": "c"
            },
            {
                "index": 5,
                "a": 60,
                "b": null,
                "index_a": "baz",
                "index_b": "a"
            }
        ],
        "df_viewer_config": {
            "pinned_rows": [
                {
                    "primary_key_val": "dtype",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                },
                {
                    "primary_key_val": "histogram",
                    "displayer_args": {
                        "displayer": "histogram"
                    }
                }
            ],
            "column_config": [
                {
                    "displayer_args": {
                        "displayer": "float",
                        "min_fraction_digits": 0,
                        "max_fraction_digits": 0
                    },
                    "col_name": "a",
                    "header_name": "foo_col"
                },
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "b"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_name": "b",
                    "header_name": "bar_col"
                }
            ],
          left_col_configs:left_col_configs2,
          "extra_grid_config": {},
          "component_config": {}
        },
        "secondary_df_viewer_config": {
            "pinned_rows": [],
            "column_config": [],
            "left_col_configs": [
                {
                    "col_name": "index",
                    "header_name": "index",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                }
            ]
        },
      "summary_stats_data": [],
    }
} 


//ddd.get_multiindex_index_df()
export const get_multiindex_index_df :Story = {
    "args": {
        "data": [
            {
                "index": 0,
                "a": 10,
                "b": "foo",
                "index_a": "foo",
                "index_b": "a"
            },
            {
                "index": 1,
                "a": 20,
                "b": "bar",
                "index_a": "foo",
                "index_b": "b"
            },
            {
                "index": 2,
                "a": 30,
                "b": "baz",
                "index_a": "bar",
                "index_b": "a"
            },
            {
                "index": 3,
                "a": 40,
                "b": "quux",
                "index_a": "bar",
                "index_b": "b"
            },
            {
                "index": 4,
                "a": 50,
                "b": "boff",
                "index_a": "bar",
                "index_b": "c"
            },
            {
                "index": 5,
                "a": 60,
                "b": null,
                "index_a": "baz",
                "index_b": "a"
            }
        ],
        "df_viewer_config": {
            "pinned_rows": [
                {
                    "primary_key_val": "dtype",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                },
                {
                    "primary_key_val": "histogram",
                    "displayer_args": {
                        "displayer": "histogram"
                    }
                }
            ],
            "column_config": [
                {
                    "displayer_args": {
                        "displayer": "float",
                        "min_fraction_digits": 0,
                        "max_fraction_digits": 0
                    },
                    "col_name": "a",
                    "header_name": "foo_col"
                },
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "b"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_name": "b",
                    "header_name": "bar_col"
                }
            ],
            "left_col_configs": [
                {
		  header_name:"",
                  "col_name": "index_a",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                },
                {
                  header_name:"",
                    "col_name": "index_b",
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "ag_grid_specs": {
                        "headerClass": [
                            "last-index-header-class"
                        ],
                        "cellClass": [
                            "last-index-cell-class"
                        ]
                    }
                }
            ],
            "extra_grid_config": {},
            "component_config": {}
        },
        "secondary_df_viewer_config": {
            "pinned_rows": [],
            "column_config": [],
            "left_col_configs": [
                {
                    "col_name": "index",
                    "header_name": "index",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                }
            ]
        },
        "summary_stats_data": []
    }
}


//get_multiindex_index_multiindex_with_names_cols_df
export const get_multiindex_index_multiindex_with_names_cols_df :Story = {
    "args": {
        "data": [
            {
                "index": 0,
                "a": 10,
                "b": 20,
                "c": 30,
                "d": 40,
                "e": 50,
                "f": 60.0,
                "index_a": "foo",
                "index_b": "a"
            },
            {
                "index": 1,
                "a": "foo",
                "b": "bar",
                "c": "baz",
                "d": "quux",
                "e": "boff",
                "f": null,
                "index_a": "foo",
                "index_b": "b"
            },
            {
                "index": 2,
                "a": 10,
                "b": 20,
                "c": 30,
                "d": 40,
                "e": 50,
                "f": 60.0,
                "index_a": "bar",
                "index_b": "a"
            },
            {
                "index": 3,
                "a": "foo",
                "b": "bar",
                "c": "baz",
                "d": "quux",
                "e": "boff",
                "f": null,
                "index_a": "bar",
                "index_b": "b"
            },
            {
                "index": 4,
                "a": 10,
                "b": 20,
                "c": 30,
                "d": 40,
                "e": 50,
                "f": 60.0,
                "index_a": "bar",
                "index_b": "c"
            },
            {
                "index": 5,
                "a": "foo",
                "b": "bar",
                "c": "baz",
                "d": "quux",
                "e": "boff",
                "f": null,
                "index_a": "baz",
                "index_b": "a"
            }
        ],
        "df_viewer_config": {
            "pinned_rows": [
                {
                    "primary_key_val": "dtype",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                },
                {
                    "primary_key_val": "histogram",
                    "displayer_args": {
                        "displayer": "histogram"
                    }
                }
            ],
            "column_config": [
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "a"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_path": [
                        "foo",
                        "a"
                    ],
                    "field": "a"
                },
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "b"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_path": [
                        "foo",
                        "b"
                    ],
                    "field": "b"
                },
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "c"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_path": [
                        "bar",
                        "a"
                    ],
                    "field": "c"
                },
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "d"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_path": [
                        "bar",
                        "b"
                    ],
                    "field": "d"
                },
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "e"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_path": [
                        "bar",
                        "c"
                    ],
                    "field": "e"
                },
                {
                    "displayer_args": {
                        "displayer": "float",
                        "min_fraction_digits": 3,
                        "max_fraction_digits": 3
                    },
                    "col_path": [
                        "baz",
                        "a"
                    ],
                    "field": "f"
                }
            ],
            "left_col_configs": [
                {
                    "col_path": [
                        "",
                        "",
                    ],
                    "field": "index_a",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                },
                {
                    "col_path": [
                        "level_a",
                        "level_b",
                    ],
                    "field": "index_b",
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "ag_grid_specs": {
                        "headerClass": [
                            "last-index-header-class"
                        ],
                        "cellClass": [
                            "last-index-cell-class"
                        ]
                    }
                }
            ],
            "extra_grid_config": {},
            "component_config": {}
        },
        "secondary_df_viewer_config": {
            "pinned_rows": [],
            "column_config": [],
            "left_col_configs": [
                {
                    "col_name": "index",
                    "header_name": "index",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                }
            ]
        },
        "summary_stats_data": []
    }
}

//get_multiindex3_index_df
export const get_multiindex3_index_df :Story = {
    "args": {
        "data": [
            {
                "index": 0,
                "a": 10,
                "b": "foo",
                "index_a": "foo",
                "index_b": "a",
                "index_c": 3
            },
            {
                "index": 1,
                "a": 20,
                "b": "bar",
                "index_a": "foo",
                "index_b": "b",
                "index_c": 2
            },
            {
                "index": 2,
                "a": 30,
                "b": "baz",
                "index_a": "bar",
                "index_b": "a",
                "index_c": 1
            },
            {
                "index": 3,
                "a": 40,
                "b": "quux",
                "index_a": "bar",
                "index_b": "b",
                "index_c": 3
            },
            {
                "index": 4,
                "a": 50,
                "b": "boff",
                "index_a": "bar",
                "index_b": "c",
                "index_c": 5
            },
            {
                "index": 5,
                "a": 60,
                "b": null,
                "index_a": "baz",
                "index_b": "a",
                "index_c": 6
            }
        ],
        "df_viewer_config": {
            "pinned_rows": [
                {
                    "primary_key_val": "dtype",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                },
                {
                    "primary_key_val": "histogram",
                    "displayer_args": {
                        "displayer": "histogram"
                    }
                }
            ],
            "column_config": [
                {
                    "displayer_args": {
                        "displayer": "float",
                        "min_fraction_digits": 0,
                        "max_fraction_digits": 0
                    },
                    "col_name": "a",
                    "header_name": "foo_col"
                },
                {
                    "tooltip_config": {
                        "tooltip_type": "simple",
                        "val_column": "b"
                    },
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_name": "b",
                    "header_name": "bar_col"
                },
                {
                    "displayer_args": {
                        "displayer": "float",
                        "min_fraction_digits": 0,
                        "max_fraction_digits": 0
                    },
                    "col_name": "a",
                    "header_name": "foo_col"
                },
                {
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_name": "b",
                    "header_name": "bar_col"
                },
                {
                    "displayer_args": {
                        "displayer": "float",
                        "min_fraction_digits": 0,
                        "max_fraction_digits": 0
                    },
                    "col_name": "a",
                    "header_name": "foo_col"
                },
                {
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_name": "b",
                    "header_name": "bar_col"
                },
                {
                    "displayer_args": {
                        "displayer": "float",
                        "min_fraction_digits": 0,
                        "max_fraction_digits": 0
                    },
                    "col_name": "a",
                    "header_name": "foo_col"
                },
                {
                    "displayer_args": {
                        "displayer": "obj"
                    },
                    "col_name": "b",
                    "header_name": "bar_col"
                },
            ],

            "left_col_configs": [
                {
                    "header_name": "",
                    "col_name": "index_a",
                    "displayer_args": {
                        "displayer": "obj"
                    },
                  "ag_grid_specs": {pinned:'left',}
                },
                {
                    "header_name": "",
                    "col_name": "index_b",
                    "displayer_args": {
                        "displayer": "obj"
                    },
                  "ag_grid_specs": {pinned:'left',}
                },
                {
                    "header_name": "",
                    "col_name": "index_c",
                    "displayer_args": {
                        "displayer": "obj"
                    },
                  "ag_grid_specs": {pinned:'left',}
                }
            ],
            "extra_grid_config": {},
            "component_config": {}
        },
        "secondary_df_viewer_config": {
            "pinned_rows": [],
            "column_config": [],
            "left_col_configs": [
                {
                    "col_name": "index",
                    "header_name": "index",
                    "displayer_args": {
                        "displayer": "obj"
                    }
                }
            ]
        },
        "summary_stats_data": []
    }
}
