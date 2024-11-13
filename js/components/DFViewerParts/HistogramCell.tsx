import _ from 'lodash';
import React from 'react';
import { createPortal } from 'react-dom';

import { Bar, BarChart, Tooltip } from 'recharts';

export interface HistogramNode {
  name: string;
  population: number;
}

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

const CustomTooltip = ({ active, payload, label, screenCoords }: any) => {
  if (active && payload && payload.length && screenCoords) {
    // console.log("payload", payload, "label", label);
    // console.log("payload[0].payload", payload[0].payload, payload[0].payload.name)
    const name = payload[0].payload.name;
    return createPortal(
      <div
        style={{
          backgroundColor: '#eee',
          padding: '5px 10px 5px 10px',
          color: '#111',
          position: 'absolute',
          top: screenCoords.y + 10,
          left: screenCoords.x + 10,
        }}
      >
        <p className="label">{`${name} : ${payload[0].value}`}</p>
      </div>,
      document.body
    );
  }

  return null;
};

export const HistogramCell = (props: any) => {
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

  // used to prevent duplicate IDs which lead to a nasty bug where patterns aren't applied
  // https://github.com/paddymul/buckaroo/issues/292
  const gensym = (base: string) => {
    const id = `${base}-${crypto.randomUUID()}`;
    return [id, `url(#${id})`];
  };
  const [starId, starUrl] = gensym('star');
  const [stripeId, stripeUrl] = gensym('stripe');
  const [circleId, circleUrl] = gensym('circle');
  const [checkersId, checkersUrl] = gensym('checkers');
  const [leafsId, leafsUrl] = gensym('leafs');
  const [screenCoords, setScreenCoords] = React.useState<{
    x: number;
    y: number;
  } | null>(null);
  return (
    <div className="histogram-component">
      <BarChart
        width={100}
        height={24}
        barGap={1}
        data={histogram}
        onClick={dumbClickHandler}
        onMouseMove={(_, e) => {
          // console.log(e);
          setScreenCoords({ x: e.clientX, y: e.clientY });
        }}
      >
        <defs>
          <pattern
            id={starId}
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
            id={stripeId}
            width="4"
            height="4"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="2" height="4" fill="red" />
          </pattern>
          <pattern
            id={circleId}
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
            id={checkersId}
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
            id={leafsId}
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
        <Bar
          dataKey="population"
          stroke="#000"
          fill="gray"
          stackId="stack"
          isAnimationActive={false}
        />
        <Bar
          dataKey="tail"
          stroke="#000"
          fill="gray"
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
          stroke="#000"
          fill="#fff"
          stackId="stack"
          isAnimationActive={false}
        />
        <Bar
          dataKey="cat_pop"
          stroke="pink"
          fill={circleUrl}
          stackId="stack"
          isAnimationActive={false}
        />
        <Bar
          dataKey="unique"
          stroke="#0f0"
          fill={checkersUrl}
          stackId="stack"
          isAnimationActive={false}
        />
        <Bar
          dataKey="longtail"
          stroke="teal"
          fill={leafsUrl}
          stackId="stack"
          isAnimationActive={false}
        />
        <Bar
          dataKey="user1"
          stroke="teal"
          fill={starUrl}
          stackId="stack"
          isAnimationActive={false}
        />
        <Bar
          dataKey="NA"
          fill={stripeUrl}
          stackId="stack"
          isAnimationActive={false}
        />
        <Tooltip
          formatter={formatter}
          allowEscapeViewBox={{ x: true, y: true }}
          wrapperStyle={{ zIndex: 99999999, color: '#111' }}
          content={(props) => (
            <CustomTooltip {...props} screenCoords={screenCoords} />
          )}
        />
      </BarChart>
    </div>
  );
};
