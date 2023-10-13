/**
 * This module contains the standard library from rechart so that base rechart code cna be imported with the minimum amount of rewriting
 */

import _ from 'lodash';
import { CSSProperties, ReactNode } from 'react';
export { Global, DefaultTooltipContent } from 'recharts';

//export Global;

//import { AnimationDuration, AnimationTiming } from '../util/types';
/** The type of easing function to use for animations */
export type AnimationTiming =
  | 'ease'
  | 'ease-in'
  | 'ease-out'
  | 'ease-in-out'
  | 'linear';
/** Specifies the duration of animation, the unit of this option is ms. */
export type AnimationDuration = number;

export type TooltipType = 'none';
export type ValueType = number | string | Array<number | string>;
export type NameType = number | string;

export type Formatter<TValue extends ValueType, TName extends NameType> = (
  value: TValue,
  name: TName,
  item: Payload<TValue, TName>,
  index: number,
  payload: Array<Payload<TValue, TName>>
) => [React.ReactNode, TName] | React.ReactNode;

export interface Payload<TValue extends ValueType, TName extends NameType> {
  type?: TooltipType;
  color?: string;
  formatter?: Formatter<TValue, TName>;
  name?: TName;
  value?: TValue;
  unit?: ReactNode;
  dataKey?: string | number;
  payload?: any;
  chartType?: string;
  stroke?: string;
  strokeDasharray?: string | number;
  strokeWidth?: number | string;
}

export interface DefaultProps<
  TValue extends ValueType,
  TName extends NameType
> {
  separator?: string;
  wrapperClassName?: string;
  labelClassName?: string;
  formatter?: Formatter<TValue, TName>;
  contentStyle?: CSSProperties;
  itemStyle?: CSSProperties;
  labelStyle?: CSSProperties;
  labelFormatter?: (
    label: any,
    payload: Array<Payload<TValue, TName>>
  ) => ReactNode;
  label?: any;
  payload?: Array<Payload<TValue, TName>>;
  itemSorter?: (item: Payload<TValue, TName>) => number | string;
}

export const isNumber = (value: unknown): value is number =>
  _.isNumber(value) && !_.isNaN(value);
export const isNumOrStr = (value: unknown): value is number | string =>
  isNumber(value as number) || _.isString(value);
