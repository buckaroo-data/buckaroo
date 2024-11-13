import React, {useState} from 'react';
import _ from 'lodash';

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
        index: '_type',
        a: 'integer',
        b: 'float'
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

function genInt(len, min, max) {
    const a = new Array(len);
    return _.map(a, (a) => _.random(min, max));
}

function genIntSeq(len:number) {
    const a = new Array(len);
    for(var i =0; i < len; i++){
        a[i] = i;
    }
    return a;
}

function genString(items: number, minLen: number, maxLen: number): string[] {
    const a = new Array(items);
    const randStrings = _.map(a, () => {
        const strLen = _.random(minLen, maxLen);
        const b = new Array(strLen);
        const randLenStr = _.map(b, () => {
            return String.fromCharCode(_.random(65, 90));
        }).join('');
        return randLenStr;
    });
    return randStrings;
}

const dictOfListsToListOfDicts = (a: Record<string, any[]>): Record<string, any>[] => {
    const firstKey = _.keys(a)[0];
    const data: Record<string, any>[] = _.map(a[firstKey], (_val, idx): Record<string, any> => {
        const pairs: [string, any][] = _.map(a, (arr, key) => {
            return [key, arr[idx]];
        });
        const row: Record<string, any> = _.fromPairs(pairs);
        return row;
    });
    return data;
};

export default function DFViewerExString() {
    const [activeCol, setActiveCol] = useState('tripduration');
    const samples = 300;
    const data = dictOfListsToListOfDicts({
        index: genIntSeq(samples),
        a: genInt(samples, 2, 30),
        b: genInt(samples, 10, 8),
        c: genString(samples, 3, 10),
        d: genInt(samples, 100, 999),
        e: genInt(samples, -30_000, 55_123_123),
        f: genString(samples, 3, 70),
        g: genInt(samples, -3, 55)
    });
    //const current: {'df':DFData, 'df_viewer_config':DFViewerConfig, 'summary_stats_data':DFData} =   {
    const current: {df: any; df_viewer_config: any; summary_stats_data: any} = {
        df: data,
        df_viewer_config: {
            pinned_rows: [
                {
                    primary_key_val: 'dtype',
                    displayer_args: {
                        displayer: 'obj'
                    },

		    
                },
                {
                    primary_key_val: 'histogram',
                    displayer_args: {
                        displayer: 'histogram'
                    },
                }
            ],
            component_config: {height_fraction: 1.15},

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
                    },
		    "tooltip_config": {
			"tooltip_type": "simple",
			"val_column": "b"}
                },
                {
                    col_name: 'c',
                    displayer_args: {
                        displayer: 'obj'
                    }
                },
                {
                    col_name: 'd',
                    displayer_args: {
                        displayer: 'obj'
                    }
                },
                {
                    col_name: 'e',
                    displayer_args: {
                        displayer: 'obj'
                    }
                },
                {
                    col_name: 'f',
                    displayer_args: {
                        displayer: 'obj'
                    }
                },
                {
                    col_name: 'g',
                    displayer_args: {
                        displayer: 'obj'
                    }
                }
            ]
        },
        summary_stats_data: summary_stats_data
    };

    return (
        <extraComponents.StaticWrapDFViewerInfinite
            df_data={current.df}
            df_viewer_config={current.df_viewer_config}
            summary_stats_data={current.summary_stats_data}
        />
    );
}
