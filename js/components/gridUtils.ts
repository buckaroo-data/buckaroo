import {
  ColDef,
  ValueFormatterFunc,
  ValueFormatterParams,
} from 'ag-grid-community';
import { DFWhole, DFColumn, ColumnHint } from './staticData';
import _ from 'lodash';
export const updateAtMatch = (
  cols: ColDef[],
  key: string,
  subst: Partial<ColDef>,
  negative: Partial<ColDef>
) => {
  const retColumns = cols.map((x) => {
    if (x.field === key) {
      return { ...x, ...subst };
    } else {
      return { ...x, ...negative };
    }
  });
  return retColumns;
};

/*
  this code should all be unit tested and in examples. Examples will
  show potential developers how this behaves. Examples should be made
  inside of AG-Grid, and independently.
  */

export const intFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

const floatFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

export const anyFormatter = (params: ValueFormatterParams): string => {
  const val = params.value;
  try {
    const num = Number(val);
    if (val === null) {
      return '';
    } else if (val === undefined) {
      return '';
    } else if (Number.isFinite(num)) {
      if (Number.isInteger(num)) {
        const formatted = intFormatter.format(num);
        return `${formatted}    `;
      } else {
        return floatFormatter.format(num);
      }
    }
  } catch (e: any) {
    //console.log("formatting error", val, e);
  }
  return val;
};

const getNumericFormatter = (totalWidth: number) => {
  const formatter = new Intl.NumberFormat('en-US');
  const numericFormatter = (params: ValueFormatterParams): string => {
    const val = params.value;
    if (val === null) {
      return '';
    }
    return formatter.format(params.value).padStart(totalWidth, ' ');
  };
  return numericFormatter;
};

function getFormatter(hint: ColumnHint): ValueFormatterFunc<unknown> {
  if (hint === undefined || hint.is_numeric === false) {
    return anyFormatter;
  } else {
    const commas = Math.floor(hint.max_digits / 3);

    if (hint.is_integer) {
      const totalWidth = commas + hint.max_digits;
      return getNumericFormatter(totalWidth);
    } else {
      return (params: ValueFormatterParams): string => {
        if (params.value === null) {
          return '';
        }
        return floatFormatter.format(params.value);
      };
    }
  }
}

export function dfToAgrid(tdf: DFWhole): [ColDef[], unknown[]] {
  const fields = tdf.schema.fields;
  //console.log("tdf", tdf);
  //console.log("hints", tdf.table_hints);
  const retColumns: ColDef[] = fields.map((f: DFColumn) => {
    //console.log(f.name, tdf.table_hints[f.name])
    const colDef: ColDef = {
      field: f.name,
      headerName: f.name,
      valueFormatter: getFormatter(
        _.get(tdf.table_hints, f.name, { is_numeric: false })
      ),
    };
    if (f.name === 'index') {
      colDef.pinned = 'left';
    }
    return colDef;
  });
  return [retColumns, tdf.data];
}
