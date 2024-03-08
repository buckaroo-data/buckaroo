import _ from 'lodash';
import React from 'react';
import { createPortal } from 'react-dom';

import {
  BarChart,
  Bar,
  //Tooltip,
  //Legend,
  //Cell, XAxis, YAxis, CartesianGrid, , ResponsiveContainer,
} from 'recharts';
import { Tooltip } from '../../vendor/RechartTooltip';

import { isNumOrStr, ValueType } from '../../vendor/RechartExtra';
import { ValueFormatterFunc } from 'ag-grid-community';

function defaultFormatter<TValue extends ValueType>(value: TValue) {
  return _.isArray(value) && isNumOrStr(value[0]) && isNumOrStr(value[1])
    ? (value.join(' ~ ') as TValue)
    : value;
}

export const bakedData = [
  {
    name: 'Page A',
    population: 4000,
  },
  {
    name: 'Page B',
    population: 3000,
  },
  {
    name: 'Page C',
    population: 2000,
  },
  {
    name: 'Page D',
    population: 2780,
  },
  {
    name: 'Page E',
    population: 1890,
  },
];

export const makeData = (histogram: number[]) => {
  const accum = [];
  for (let i = 0; i < histogram.length; i++) {
    accum.push({
      name: `${i + 1}/${histogram.length}`,
      population: histogram[i],
    });
  }
  //console.log('accum', accum)
  return accum;
};

export const formatter = (value: any, name: any, props: any) => {
  if (props.payload.name === 'longtail') {
    return [value, name];
  } else {
    return [value, props.payload.name];
  }
};

export function FloatingTooltip({ items, x, y }: any) {
  const offset = 30;
  const renderedItems = items.map(
    (name: [string, number], value: number | string) => {
      const [realName, realValue] = name;
      const formattedVal = realValue === 0 ? '<1' : realValue;
      return (
        <React.Fragment>
          <dt>{realName}</dt>
          <dd>{formattedVal}%</dd>
        </React.Fragment>
      );
    }
  );
  return createPortal(
    <div
      className="floating-tooltip"
      style={{ position: 'absolute', top: y + offset, left: x + offset }}
    >
      <dl>{renderedItems}</dl>
    </div>,
    document.body
  );
}

export const ToolTipAdapter = (args: any) => {
  const { active, formatter, payload } = args;
  if (active && payload && payload.length) {
    const renderContent2 = () => {
      //const items = (itemSorter ? _.sortBy(payload, itemSorter) : payload).map((entry, i) => {
      const items = payload.map((entry: any, i: number) => {
        if (entry.type === 'none') {
          return null;
        }

        const finalFormatter = entry.formatter || formatter || defaultFormatter;
        const { value, name } = entry;
        let finalValue: React.ReactNode = value;
        let finalName: React.ReactNode = name;
        if (finalFormatter && finalValue !== null && finalName !== null) {
          const formatted = finalFormatter(value, name, entry, i, payload);
          if (Array.isArray(formatted)) {
            [finalValue, finalName] = formatted;
          } else {
            finalValue = formatted;
          }
        }

        return [finalName, finalValue];
      });
      return items;
    };
    return (
      <div className="custom-tooltip">
        <FloatingTooltip
          items={renderContent2()}
          x={args.box.x}
          y={args.box.y}
        />
      </div>
    );
  }

  return null;
};

export const getTextCellRenderer = (formatter: ValueFormatterFunc<any>) => {
  const TextCellRenderer = (props: any) => {
    return <span>{formatter(props)}</span>;
  };
  return TextCellRenderer;
};

export const LinkCellRenderer = (props: any) => {
  return <a href={props.value}>{props.value}</a>;
};

export const Base64PNGDisplayer = (props: any) => {
  const imgString = 'data:image/png;base64,' + props.value;
  return <img src={imgString}></img>;
};

export const SVGDisplayer = (props: any) => {
  const markup = { __html: props.value };

  return (
    <div //style={{border:'1px solid red', borderBottom:'1px solid green'}}
      dangerouslySetInnerHTML={markup}
    ></div>
  );
};

export const HistogramCell = (props: any) => {
  //debugger;
  if (props === undefined || props.value === undefined) {
    return <span></span>;
  }
  const histogram = props.value;
  //for key "index", the value is "histogram"
  // this causes ReChart to blow up, so we check to see if it's an array
  if (histogram === undefined || !_.isArray(histogram)) {
    return <span></span>;
  }
  const dumbClickHandler = (rechartsArgs: any, _unused_react: any) => {
    // I can't find the type for rechartsArgs
    // these are probably the keys we care about
    // activeTooltipIndex
    // activeLabel
    console.log('dumbClickHandler', rechartsArgs);
  };

  return (
    <div className="histogram-component">
      <BarChart
        width={100}
        height={24}
        barGap={1}
        data={histogram}
        onClick={dumbClickHandler}
      >
        <defs>
          <pattern
            id="star"
            width="10"
            height="10"
            patternUnits="userSpaceOnUse"
          >
            <polygon
              stroke="pink"
              points="0,0 2,5 0,10 5,8 10,10 8,5 10,0 5,2"
            />
          </pattern>
          <pattern
            id="stripe"
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="2" height="4" fill="red" />
          </pattern>
          <pattern
            id="circles"
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
          >
            <circle
              data-color="outline"
              stroke="pink"
              cx=".5"
              cy=".5"
              r="1.5"
            ></circle>
          </pattern>

          <pattern
            id="checkers"
            x="0"
            y="0"
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
          >
            <rect stroke="#0f0" x="0" width="2" height="2" y="0"></rect>
            <rect x="2" width="2" height="2" y="2"></rect>
          </pattern>

          <pattern
            id="leafs"
            x="0"
            y="0"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="translate(1, 1) rotate(0) skewX(0)"
          >
            <svg width="5" height="5" viewBox="0 0 100 100">
              <g fill="teal" opacity="1">
                <path d="M99.9557 99.9557C45.4895 98.3748 1.6248 54.5101 0.0439453 0.0439453C54.5101 1.6248 98.3748 45.4895 99.9557 99.9557Z"></path>
              </g>
            </svg>
          </pattern>
        </defs>
        <Bar dataKey="population" stroke="#000" fill="gray" stackId="stack" />
        <Bar dataKey="tail" stroke="#000" fill="gray" stackId="stack" />
        <Bar dataKey="true" stroke="#00f" fill="#00f" stackId="stack" />
        <Bar dataKey="false" stroke="#000" fill="#fff" stackId="stack" />
        <Bar
          dataKey="cat_pop"
          stroke="pink"
          fill="url(#circles)"
          stackId="stack"
        />
        <Bar
          dataKey="unique"
          stroke="#0f0"
          fill="url(#checkers)"
          stackId="stack"
        />
        <Bar
          dataKey="longtail"
          stroke="teal"
          fill="url(#leafs)"
          stackId="stack"
        />
        <Bar dataKey="NA" fill="url(#stripe)" stackId="stack" />

        <Tooltip
          formatter={formatter}
          labelStyle={{ display: 'None' }}
          wrapperStyle={{ zIndex: 999991 }}
          contentStyle={{ color: 'black' }}
          content={<ToolTipAdapter />}
          offset={20}
          allowEscapeViewBox={{ x: true }}
        />
      </BarChart>
    </div>
  );
};
