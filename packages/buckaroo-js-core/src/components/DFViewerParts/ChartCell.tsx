import { isArray } from "lodash-es";
import React from "react";
import { createPortal } from "react-dom";

import { Area, ComposedChart, Line, Tooltip, Bar } from "recharts";
import { ChartDisplayerA } from "./DFWhole";


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
    'unique'?: number;
    'barRed'?: number;
    'barBlue'?: number;
    'barGray'?: number;
    'barCustom1'?: number;
    'barCustom2'?: number;
    'barCustom3'?: number;
    'lineRed'?: number;
    'lineBlue'?: number;
    'lineGray'?: number;
    'lineCustom1'?: number;
    'lineCustom2'?: number;
    'lineCustom3'?: number;
    'areaRed'?: number;
    'areaBlue'?: number;
    'areaGray'?: number;
    'areaCustom1'?: number;
    'areaCustom2'?: number;
    'areaCustom3'?: number;
    'areaUnique'?: number;
}


export const ChartColors = {
    unique: "#0f0",
    longtail: "teal",
    NA: "red",
    cat_pop: "pink",
}

export function getChartColors(scheme: 'light' | 'dark') {
    return scheme === 'light' ? {
        unique: '#228B22',
        longtail: '#006060',
        NA: '#cc0000',
        cat_pop: '#c06',
    } : ChartColors;
}


export const getChartCell = (multiChartCellProps: ChartDisplayerA) => {
    const colorDefaults = {
        custom1_color: "teal",
        custom2_color: "orange",
        custom3_color: "purple"
    }
    const passedColors = multiChartCellProps.colors ? multiChartCellProps.colors : {}
    const mergedColors = { ...colorDefaults, ...passedColors };
    const { custom1_color, custom2_color, custom3_color } = mergedColors;
    const ChartCell = (props: any) => {
        if (props === undefined) {
            return <span></span>;
        }
        const potentialHistogramArr = props.value;
        //for key "index", the value is "histogram"
        // this causes ReChart to blow up, so we check to see if it's an array
        if (potentialHistogramArr === undefined || !isArray(potentialHistogramArr)) {
            return <span></span>;
        }
        const histogramArr = potentialHistogramArr as LineObservation[];
        return TypedChartCellInner({ histogramArr });
    }

    const TypedChartCellInner = ({ histogramArr }: { histogramArr: LineObservation[] }) => {
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
                    <Bar
                        dataKey="barRed"
                        stroke="red"
                        fill="red"
                        isAnimationActive={false}
                        stackId="stack"
                    />
                    <Bar
                        dataKey="barBlue"
                        stroke="blue"
                        fill="blue"
                        isAnimationActive={false}
                        stackId="stack"
                    />
                    <Bar
                        dataKey="barGrayed"
                        stroke="gray"
                        fill="Gray"
                        isAnimationActive={false}
                        stackId="stack"
                    />
                    <Bar
                        dataKey="barCustom1"
                        stroke={custom1_color}
                        fill={custom1_color}
                        isAnimationActive={false}
                        stackId="stack"
                    />
                    <Bar
                        dataKey="barCustom2"
                        stroke={custom2_color}
                        fill={custom2_color}

                        isAnimationActive={false}
                        stackId="stack"
                    />

                    <Bar
                        dataKey="barCustom3"
                        stroke={custom3_color}
                        fill={custom3_color}

                        isAnimationActive={false}
                        stackId="stack"
                    />

                    <Line
                        type="monotone"
                        dataKey="lineRed"
                        stroke="red"
                        fill="red"
                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey="lineBlue"
                        stroke="blue"
                        fill="blue"
                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey="lineGray"
                        stroke="gray"
                        fill="gray"
                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey="lineCustom1"
                        stroke={custom1_color}
                        fill={custom1_color}

                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey="lineCustom2"
                        stroke={custom2_color}
                        fill={custom2_color}

                        isAnimationActive={false}
                    />
                    <Line
                        type="monotone"
                        dataKey="lineCustom3"
                        stroke={custom3_color}
                        fill={custom3_color}
                        isAnimationActive={false}
                    />

                    <Area
                        type="monotone"
                        dataKey="areaBlue"
                        stroke="blue"
                        fill="blue"
                        isAnimationActive={false}
                    />
                    <Area
                        type="monotone"
                        dataKey="areaRed"
                        stroke="red"
                        fill="red"
                        isAnimationActive={false}
                    />
                    <Area
                        type="monotone"
                        dataKey="areaGray"
                        stroke="gray"
                        fill="gray"
                        isAnimationActive={false}
                    />
                    <Area
                        type="monotone"
                        dataKey="areaUnique"
                        stroke={ChartColors.unique}
                        fill={ChartColors.unique}
                        isAnimationActive={false}
                    />
                    <Area
                        type="monotone"
                        dataKey="areaCustom1"
                        stroke={custom1_color}
                        fill={custom1_color}
                        isAnimationActive={false}
                    />
                    <Area
                        type="monotone"
                        dataKey="areaCustom2"
                        stroke={custom2_color}
                        fill={custom2_color}
                        isAnimationActive={false}
                    />
                    <Area
                        type="monotone"
                        dataKey="areaCustom3"
                        stroke={custom3_color}
                        fill={custom3_color}
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
    return ChartCell
}
