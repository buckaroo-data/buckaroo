import _ from "lodash";
import React from "react";
import { createPortal } from "react-dom";

import { Area, ComposedChart, Line, Tooltip } from "recharts";

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
    if (active && payload && payload.length && screenCoords) {
        // console.log("payload", payload, "label", label);
        // console.log("payload[0].payload", payload[0].payload, payload[0].payload.name)
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
                <p className="label">{`${name} : ${payload[0].value}`}</p>
            </div>,
            document.body,
        );
    }

    return null;
};


export interface LineObservation {
    'cat_pop'?: number;
    'name':string;
    'NA'?: number;
    'longtail'?: number;
    'unique'?:number;
    'population'?: number;
}


export const ChartColors = {
    unique: "#0f0",
    longtail: "teal",
    NA:"red",
    cat_pop:"pink",
}

export const LineChartCell = (props: any) => {
    debugger;
    if (props === undefined ) {
        return <span></span>;
    }
    const potentialHistogramArr = props.value;
    //for key "index", the value is "histogram"
    // this causes ReChart to blow up, so we check to see if it's an array
    if (potentialHistogramArr === undefined || !_.isArray(potentialHistogramArr)) {
        return <span></span>;
    }
    const histogramArr = potentialHistogramArr as LineObservation[];
    return TypedLineChartCell({histogramArr});
}

export const TypedLineChartCell = ({histogramArr}:{histogramArr:LineObservation[]}) => {
    const dumbClickHandler = (rechartsArgs: any, _unused_react: any) => {
        // I can't find the type for rechartsArgs
        // these are probably the keys we care about
        // activeTooltipIndex
        // activeLabel
        console.log("dumbClickHandler", rechartsArgs);
    };

    // used to prevent duplicate IDs which lead to a nasty bug where patterns aren't applied
    // https://github.com/paddymul/buckaroo/issues/292
    const [screenCoords, setScreenCoords] = React.useState<{
        x: number;
        y: number;
    } | null>(null);
    return (
        <div className="histogram-component">
            <ComposedChart
                            width={100}
                            height={24}
                            data={histogramArr}
                            onClick={dumbClickHandler}
                            onMouseMove={(_, e) => {
                                // console.log(e);
                                setScreenCoords({ x: e.clientX, y: e.clientY });
                            }}
                            >
                <Line
                    type="monotone"
                    dataKey="cat_pop"
                    stroke="#000"
                    fill="gray"
                    isAnimationActive={false}
                />
                <Area 
                    type="monotone"
                    dataKey="unique"
                    stroke={ChartColors.unique}
                    fill={ChartColors.unique}
                    isAnimationActive={false}
                />
                <Tooltip
                    formatter={formatter}
                    allowEscapeViewBox={{ x: true, y: true }}
                    wrapperStyle={{ zIndex: 99999999, color: "#111" }}
                    content={(props) => <CustomTooltip {...props} screenCoords={screenCoords} />}
                />
            </ComposedChart>
        </div>
    );
};
