import _ from 'lodash';
import { DFWhole } from './staticData';

export type setDFFunc = (newDf: DFWhole) => void;

export const requestDf = (url: string, setCallBack: setDFFunc) => {
  const retPromise = fetch(url).then(async (response) => {
    const tableDf = await response.json();
    setCallBack(tableDf);
  });
  return retPromise;
};

export const sym = (symbolName: string) => {
  return { symbol: symbolName };
};

export function replaceInArr<T>(arr: T[], old: T, subst: T): T[] {
  return arr.map((item: T) => (item === old ? subst : item));
}

export function replaceAtIdx<T>(arr: T[], idx: number, subst: T): T[] {
  return arr.map((item: T, innerIdx: number) =>
    innerIdx === idx ? subst : item
  );
}

export function replaceAtKey<T>(
  obj: Record<string, T>,
  key: string,
  subst: T
): Record<string, T> {
  const objCopy = _.clone(obj);
  objCopy[key] = subst;
  return objCopy;
}

export const objWithoutNull = (
  obj: Record<string, string>,
  extraStrips: string[] = []
) => _.pickBy(obj, (x) => ![null, undefined, ...extraStrips].includes(x));
