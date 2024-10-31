import React, {useState} from 'react';
import {extraComponents} from 'buckaroo';

const data = [
    {
        index: 0,
        a: 5,
        b: 2.8571428571
    },
    {
        index: 1,
        a: 28,
        b: 12.8571428571
    },
    {
        index: 2,
        a: 47,
        b: 2.8571428571
    },
    {
        index: 3,
        a: 4,
        b: 32.8571428571
    },
    {
        index: 4,
        a: 29,
        b: 30
    },
    {
        index: 5,
        a: 26,
        b: 38.5714285714
    },
    {
        index: 6,
        a: 29,
        b: 12.8571428571
    },
    {
        index: 7,
        a: 49,
        b: 18.5714285714
    },
    {
        index: 8,
        a: 22,
        b: 4.2857142857
    },
    {
        index: 9,
        a: 32,
        b: 35.7142857143
    },
    {
        index: 10,
        a: 19,
        b: 8.5714285714
    },
    {
        index: 11,
        a: 32,
        b: 27.1428571429
    },
    {
        index: 12,
        a: 44,
        b: 24.2857142857
    }
];

const summary_stats_data = [
    {
        index: 'dtype',
        a: 'int64',
        b: 'float64'
    },
    {
        index: 'is_numeric',
        a: true,
        b: true
    },
    {
        index: 'is_integer',
        a: true,
        b: false
    },
    {
        index: 'is_datetime',
        a: false,
        b: false
    },
    {
        index: 'is_bool',
        a: false,
        b: false
    },
    {
        index: 'is_float',
        a: false,
        b: true
    },
    {
        index: 'is_string',
        a: false,
        b: false
    },
    {
        index: 'memory_usage',
        a: 1732,
        b: 1732
    },
    {
        index: 'length',
        a: 200,
        b: 200
    },
    {
        index: 'nan_count',
        a: 0,
        b: 0
    },
    {
        index: 'value_counts',
        a: [
            7, 7, 7, 7, 7, 6, 6, 6, 6, 6, 6, 6, 5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 4, 4,
            4, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1
        ],
        b: [
            12, 11, 10, 10, 10, 10, 9, 9, 8, 8, 7, 7, 7, 7, 7, 7, 7, 7, 6, 6, 5, 5, 5, 4, 4, 3, 3,
            3, 3
        ]
    },
    {
        index: 'mode',
        a: 2,
        b: 7.1428571429
    },
    {
        index: 'min',
        a: 1,
        b: 1.4285714286
    },
    {
        index: 'max',
        a: 49,
        b: 41.4285714286
    },
    {
        index: 'mean',
        a: 24.275,
        b: 19.4571428571
    },
    {
        index: 'histogram_args',
        a: {
            meat_histogram: [
                [29, 20, 11, 20, 10, 26, 16, 17, 20, 18],
                [2, 6.6, 11.2, 15.8, 20.4, 25, 29.6, 34.2, 38.8, 43.4, 48]
            ],
            normalized_populations: [
                0.1550802139, 0.1069518717, 0.0588235294, 0.1069518717, 0.0534759358, 0.1390374332,
                0.0855614973, 0.0909090909, 0.1069518717, 0.0962566845
            ],
            low_tail: 1,
            high_tail: 49
        },
        b: {
            meat_histogram: [
                [22, 30, 17, 17, 16, 22, 26, 11, 13, 12],
                [
                    2.8571428571, 6.5714285714, 10.2857142857, 14, 17.7142857143, 21.4285714286,
                    25.1428571429, 28.8571428571, 32.5714285714, 36.2857142857, 40
                ]
            ],
            normalized_populations: [
                0.1182795699, 0.1612903226, 0.0913978495, 0.0913978495, 0.0860215054, 0.1182795699,
                0.1397849462, 0.0591397849, 0.0698924731, 0.064516129
            ],
            low_tail: 1.4285714286,
            high_tail: 41.4285714286
        }
    },
    {
        index: '_type',
        a: 'integer',
        b: 'float'
    },
    {
        index: 'type',
        a: 'integer',
        b: 'float'
    },
    {
        index: 'min_digits',
        a: 1,
        b: 1
    },
    {
        index: 'max_digits',
        a: 2,
        b: 2
    },
    {
        index: 'unique_count',
        a: 3,
        b: 0
    },
    {
        index: 'empty_count',
        a: 0,
        b: 0
    },
    {
        index: 'distinct_count',
        a: 49,
        b: 29
    },
    {
        index: 'distinct_per',
        a: 0.245,
        b: 0.145
    },
    {
        index: 'empty_per',
        a: 0,
        b: 0
    },
    {
        index: 'unique_per',
        a: 0.015,
        b: 0
    },
    {
        index: 'nan_per',
        a: 0,
        b: 0
    },
    {
        index: 'histogram',
        a: [
            {
                name: '1 - 1.0',
                tail: 1
            },
            {
                name: '2-7',
                population: 16
            },
            {
                name: '7-11',
                population: 11
            },
            {
                name: '11-16',
                population: 6
            },
            {
                name: '16-20',
                population: 11
            },
            {
                name: '20-25',
                population: 5
            },
            {
                name: '25-30',
                population: 14
            },
            {
                name: '30-34',
                population: 9
            },
            {
                name: '34-39',
                population: 9
            },
            {
                name: '39-43',
                population: 11
            },
            {
                name: '43-48',
                population: 10
            },
            {
                name: '49.0 - 49',
                tail: 1
            }
        ],
        b: [
            {
                name: '1.4285714285714286 - 1.4285714285714286',
                tail: 1
            },
            {
                name: '3-7',
                population: 12
            },
            {
                name: '7-10',
                population: 16
            },
            {
                name: '10-14',
                population: 9
            },
            {
                name: '14-18',
                population: 9
            },
            {
                name: '18-21',
                population: 9
            },
            {
                name: '21-25',
                population: 12
            },
            {
                name: '25-29',
                population: 14
            },
            {
                name: '29-33',
                population: 6
            },
            {
                name: '33-36',
                population: 7
            },
            {
                name: '36-40',
                population: 6
            },
            {
                name: '41.42857142857143 - 41.42857142857143',
                tail: 1
            }
        ]
    }
];

export default function DFViewerExString() {
    const [activeCol, setActiveCol] = useState('tripduration');

    //const dfvConfig:DFViewerConfig = {

    const dfvConfig: any = {
        pinned_rows: [
            {
                primary_key_val: 'dtype',
                displayer_args: {
                    displayer: 'obj'
                }
            },
            {
                primary_key_val: 'histogram',
                displayer_args: {
                    displayer: 'histogram'
                }
            }
        ],
        column_config: [
            {
                col_name: 'index',
                displayer_args: {
                    displayer: 'obj'
                }
            },
            {
                col_name: 'a',
                displayer_args: {
                    displayer: 'obj'
                }
            },
            {
                col_name: 'b',
                displayer_args: {
                    displayer: 'obj'
                }
            }
        ]
    };

    //   {
    //   "pinned_rows": [
    //     {
    //       "primary_key_val": "dtype",
    //       "displayer_args": {
    //         "displayer": "obj"
    //       }
    //     },
    // 	{
    // 	  "primary_key_val": "histogram",
    // 	  "displayer_args": {
    // 	    "displayer": "histogram"
    // 	  }
    // 	}
    //   ],
    //   "column_config": [
    //     {
    //       "col_name": "index",
    //       "displayer_args": {
    //         "displayer": "obj"
    //       }
    //     },
    //     {
    //       "col_name": "a",
    //       "displayer_args": {
    //         "displayer": "obj"
    //       }
    //     },
    //     {
    //       "col_name": "b",
    //       "displayer_args": {
    //         "displayer": "obj"
    //       }
    //     }
    //   ]
    // }
    //const current: {'df':DFData, 'df_viewer_config':DFViewerConfig, 'summary_stats_data':DFData} =   {

    const current: {df: any; df_viewer_config: any; summary_stats_data: any} = {
        df: [],
        df_viewer_config: {
            pinned_rows: [
                {
                    primary_key_val: 'dtype',
                    displayer_args: {
                        displayer: 'obj'
                    }
                },
                {
                    primary_key_val: 'histogram',
                    displayer_args: {
                        displayer: 'histogram'
                    }
                }
            ],
            column_config: [
                {
                    col_name: 'index',
                    displayer_args: {
                        displayer: 'obj'
                    }
                },
                {
                    col_name: 'a',
                    displayer_args: {
                        displayer: 'obj'
                    }
                },
                {
                    col_name: 'b',
                    displayer_args: {
                        displayer: 'obj'
                    }
                }
            ]
        },
        summary_stats_data: [
            {
                index: 'dtype',
                a: 'int64',
                b: 'float64'
            },
            {
                index: 'is_numeric',
                a: true,
                b: true
            },
            {
                index: 'is_integer',
                a: true,
                b: false
            },
            {
                index: 'is_datetime',
                a: false,
                b: false
            },
            {
                index: 'is_bool',
                a: false,
                b: false
            },
            {
                index: 'is_float',
                a: false,
                b: true
            },
            {
                index: 'is_string',
                a: false,
                b: false
            },
            {
                index: 'memory_usage',
                a: 1732,
                b: 1732
            },
            {
                index: 'length',
                a: 200,
                b: 200
            },
            {
                index: 'nan_count',
                a: 0,
                b: 0
            },
            {
                index: 'value_counts',
                a: [
                    12, 12, 9, 8, 7, 7, 7, 7, 7, 6, 6, 5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4,
                    4, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1
                ],
                b: [
                    11, 11, 11, 9, 9, 9, 9, 8, 8, 8, 8, 7, 7, 7, 7, 7, 7, 7, 6, 6, 5, 5, 5, 5, 4, 4,
                    4, 4, 2
                ]
            },
            {
                index: 'mode',
                a: 6,
                b: 1.4285714286
            },
            {
                index: 'min',
                a: 1,
                b: 1.4285714286
            },
            {
                index: 'max',
                a: 49,
                b: 41.4285714286
            },
            {
                index: 'mean',
                a: 23.375,
                b: 21.5285714286
            },
            {
                index: 'histogram_args',
                a: {
                    meat_histogram: [
                        [33, 18, 13, 22, 11, 18, 20, 15, 17, 23],
                        [2, 6.6, 11.2, 15.8, 20.4, 25, 29.6, 34.2, 38.8, 43.4, 48]
                    ],
                    normalized_populations: [
                        0.1736842105, 0.0947368421, 0.0684210526, 0.1157894737, 0.0578947368,
                        0.0947368421, 0.1052631579, 0.0789473684, 0.0894736842, 0.1210526316
                    ],
                    low_tail: 1,
                    high_tail: 48.01
                },
                b: {
                    meat_histogram: [
                        [13, 23, 12, 23, 15, 22, 23, 10, 21, 16],
                        [
                            2.8571428571, 6.5714285714, 10.2857142857, 14, 17.7142857143,
                            21.4285714286, 25.1428571429, 28.8571428571, 32.5714285714,
                            36.2857142857, 40
                        ]
                    ],
                    normalized_populations: [
                        0.0730337079, 0.1292134831, 0.0674157303, 0.1292134831, 0.0842696629,
                        0.1235955056, 0.1292134831, 0.0561797753, 0.1179775281, 0.0898876404
                    ],
                    low_tail: 1.4285714286,
                    high_tail: 41.4285714286
                }
            },
            {
                index: '_type',
                a: 'integer',
                b: 'float'
            },
            {
                index: 'type',
                a: 'integer',
                b: 'float'
            },
            {
                index: 'min_digits',
                a: 1,
                b: 1
            },
            {
                index: 'max_digits',
                a: 2,
                b: 2
            },
            {
                index: 'unique_count',
                a: 5,
                b: 0
            },
            {
                index: 'empty_count',
                a: 0,
                b: 0
            },
            {
                index: 'distinct_count',
                a: 49,
                b: 29
            },
            {
                index: 'distinct_per',
                a: 0.245,
                b: 0.145
            },
            {
                index: 'empty_per',
                a: 0,
                b: 0
            },
            {
                index: 'unique_per',
                a: 0.025,
                b: 0
            },
            {
                index: 'nan_per',
                a: 0,
                b: 0
            },
            {
                index: 'histogram',
                a: [
                    {
                        name: '1 - 1.0',
                        tail: 1
                    },
                    {
                        name: '2-7',
                        population: 17
                    },
                    {
                        name: '7-11',
                        population: 9
                    },
                    {
                        name: '11-16',
                        population: 7
                    },
                    {
                        name: '16-20',
                        population: 12
                    },
                    {
                        name: '20-25',
                        population: 6
                    },
                    {
                        name: '25-30',
                        population: 9
                    },
                    {
                        name: '30-34',
                        population: 11
                    },
                    {
                        name: '34-39',
                        population: 8
                    },
                    {
                        name: '39-43',
                        population: 9
                    },
                    {
                        name: '43-48',
                        population: 12
                    },
                    {
                        name: '48.00999999999999 - 49',
                        tail: 1
                    }
                ],
                b: [
                    {
                        name: '1.4285714285714286 - 1.4285714285714286',
                        tail: 1
                    },
                    {
                        name: '3-7',
                        population: 7
                    },
                    {
                        name: '7-10',
                        population: 13
                    },
                    {
                        name: '10-14',
                        population: 7
                    },
                    {
                        name: '14-18',
                        population: 13
                    },
                    {
                        name: '18-21',
                        population: 8
                    },
                    {
                        name: '21-25',
                        population: 12
                    },
                    {
                        name: '25-29',
                        population: 13
                    },
                    {
                        name: '29-33',
                        population: 6
                    },
                    {
                        name: '33-36',
                        population: 12
                    },
                    {
                        name: '36-40',
                        population: 9
                    },
                    {
                        name: '41.42857142857143 - 41.42857142857143',
                        tail: 1
                    }
                ]
            }
        ]
    };

    //const working = {'df':data, 'df_viewer_config': dfvConfig, 'summary_stats_data':summary_stats_data};
    const working = {df: data, df_viewer_config: dfvConfig, summary_stats_data: summary_stats_data};

    return (
        <extraComponents.DFViewer
            df_data={current.df}
            df_viewer_config={current.df_viewer_config}
            summary_stats_data={current.summary_stats_data}
            activeCol={activeCol}
            setActiveCol={setActiveCol}
        />
    );
}
