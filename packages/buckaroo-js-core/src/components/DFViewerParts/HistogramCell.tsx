import * as _ from "lodash-es";
import React from "react";
import { createPortal } from "react-dom";

import { Bar, BarChart, Tooltip } from "recharts";
import { getChartColors } from "./ChartCell";
import { ColDef, Column, Context, GridApi } from "@ag-grid-community/core";
import { useColorScheme } from "../useColorScheme";

export interface HistogramNode {
    name: string;
    population: number;
}

export const formatter = (value: any, name: any, props: any) => {
    if (props.payload.name === "longtail") {
        return [value, name];
    } else {
        return [value, props.payload.name];
    }
};

export function FloatingTooltip({ items, x, y }: any) {
    const offset = 30;
    const renderedItems = items.map((name: [string, number], _value: number | string) => {
        const [realName, realValue] = name;
        const formattedVal = realValue === 0 ? "<1" : realValue;
        return (
            <React.Fragment>
                <dt>{realName}</dt>
                <dd>{formattedVal}%</dd>
            </React.Fragment>
        );
    });
    return createPortal(
        <div
            className="floating-tooltip"
            style={{ position: "absolute", top: y + offset, left: x + offset }}
        >
            <dl>{renderedItems}</dl>
        </div>,
        document.body,
    );
}

const CustomTooltip = ({ active, payload, screenCoords }: any) => {
    // Read this github issue for context https://github.com/recharts/recharts/issues/5181
    if (active && payload && payload.length && screenCoords) {
        const name = payload[0].payload.name;
        return createPortal(
            <div
                style={{
                    backgroundColor: "#eee",
                    padding: "5px 10px 5px 10px",
                    color: "#111",
                    position: "absolute",
                    top: screenCoords.y + 10,
                    left: screenCoords.x + 10,
                }}
            >
                <p className="label">{`${name} : ${payload[0].value}%`}</p>
            </div>,
            document.body,
        );
    }

    return null;
};


export interface HistogramBar {
    'cat_pop'?: number;
    'name':string;
    'NA'?: number;
    'longtail'?: number;
    'unique'?:number;
    'population'?: number;
}


export const HistogramCell = (props:
    {api:GridApi, colDef:ColDef,
     column:Column, context:Context, value:any}
) => {
    // relevant args here
    // https://www.ag-grid.com/react-data-grid/component-cell-renderer/
    const colorScheme = useColorScheme();
    if (props === undefined ) {
        return <span></span>;
    }
    const potentialHistogramArr = props.value;
    //for key "index", the value is "histogram"
    // this causes ReChart to blow up, so we check to see if it's an array
    if (potentialHistogramArr === undefined || !_.isArray(potentialHistogramArr)) {
        return <span></span>;
    }
  const histogramArr = potentialHistogramArr as HistogramBar[];
  //@ts-ignore
  return TypedHistogramCell({histogramArr, context:props.context, className:props.colDef.cellClass|| "", colorScheme});
}

export const TypedHistogramCell = ({histogramArr, context, className, colorScheme = 'dark'}:
    {histogramArr:HistogramBar[], context:any, className?:string, colorScheme?: 'light' | 'dark'}) => {
    const dumbClickHandler = (rechartsArgs: any, _unused_react: any) => {
        //we can access the rest of the data model through context

        // I can't find the type for rechartsArgs
        // these are probably the keys we care about
        // activeTooltipIndex
        // activeLabel
        console.log("dumbClickHandler", rechartsArgs, context);
    };

    const cc = getChartColors(colorScheme);
    const isLight = colorScheme === 'light';
    const barStroke = isLight ? '#888' : '#000';
    const barFill = isLight ? '#999' : 'gray';
    const boolFalseStroke = isLight ? '#666' : '#000';

    // used to prevent duplicate IDs which lead to a nasty bug where patterns aren't applied
    // https://github.com/paddymul/buckaroo/issues/292
    const gensym = (base: string) => {
        const id = `${base}-${crypto.randomUUID()}`;
        return [id, `url(#${id})`];
    };
    const [starId, starUrl] = gensym("star");
    const [stripeId, stripeUrl] = gensym("stripe");
    const [circleId, circleUrl] = gensym("circle");
    const [checkersId, checkersUrl] = gensym("checkers");
    const [leafsId, leafsUrl] = gensym("leafs");
    const [screenCoords, setScreenCoords] = React.useState<{
        x: number;
        y: number;
    } | null>(null);
      const classes = `histogram-component ${className}`;
      return (
	<div className={classes} >
            <BarChart
                width={100}
                height={24}
                barGap={1}
                data={histogramArr}
                onClick={dumbClickHandler}
                onMouseMove={(_, e) => {
                    // console.log(e);
                    setScreenCoords({ x: e.clientX, y: e.clientY });
                }}
            >
                <defs>
                    <pattern id={starId} width="10" height="10" patternUnits="userSpaceOnUse">
                        <polygon stroke={cc.cat_pop} points="0,0 2,5 0,10 5,8 10,10 8,5 10,0 5,2" />
                    </pattern>
                    <pattern
                        id={stripeId}
                        width="4"
                        height="4"
                        patternUnits="userSpaceOnUse"
                        patternTransform="rotate(45)"
                    >
                        <rect width="2" height="4" fill={cc.NA} />
                    </pattern>
                    <pattern id={circleId} width="4" height="4" patternUnits="userSpaceOnUse">
                        <circle data-color="outline" stroke={cc.cat_pop} cx=".5" cy=".5" r="1.5"></circle>
                    </pattern>

                    <pattern
                        id={checkersId}
                        x="0"
                        y="0"
                        width="4"
                        height="4"
                        patternUnits="userSpaceOnUse"
                    >
                        <rect stroke={cc.unique} x="0" width="2" height="2" y="0"></rect>
                        <rect x="2" width="2" height="2" y="2"></rect>
                    </pattern>

                    <pattern
                        id={leafsId}
                        x="0"
                        y="0"
                        width="6"
                        height="6"
                        patternUnits="userSpaceOnUse"
                        patternTransform="translate(1, 1) rotate(0) skewX(0)"
                    >
                        <svg width="5" height="5" viewBox="0 0 100 100">
                            <g fill={cc.longtail} opacity="1">
                                <path d="M99.9557 99.9557C45.4895 98.3748 1.6248 54.5101 0.0439453 0.0439453C54.5101 1.6248 98.3748 45.4895 99.9557 99.9557Z"></path>
                            </g>
                        </svg>
                    </pattern>
                </defs>
                <Bar
                    dataKey="population"
                    stroke={barStroke}
                    fill={barFill}
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar
                    dataKey="tail"
                    stroke={barStroke}
                    fill={barFill}
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar
                    dataKey="true"
                    stroke="#00f"
                    fill="#00f"
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar
                    dataKey="false"
                    stroke={boolFalseStroke}
                    fill="#fff"
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar
                    dataKey="cat_pop"
                    stroke={cc.cat_pop}
                    fill={circleUrl}
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar
                    dataKey="unique"
                    stroke={cc.unique}
                    fill={checkersUrl}
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar
                    dataKey="longtail"
                    stroke={cc.longtail}
                    fill={leafsUrl}
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar
                    dataKey="user1"
                    stroke={cc.longtail}
                    fill={starUrl}
                    stackId="stack"
                    isAnimationActive={false}
                />
                <Bar dataKey="NA" fill={stripeUrl}
                     stackId="stack"
                     isAnimationActive={false} />
                <Tooltip
                    formatter={formatter}
                    allowEscapeViewBox={{ x: true, y: true }}
                    wrapperStyle={{ zIndex: 99999999, color: "#111" }}
                    content={(props) => <CustomTooltip {...props} screenCoords={screenCoords} />}
                />
            </BarChart>
        </div>
    );
};
