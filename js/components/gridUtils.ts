import {
  ColDef,
  ValueFormatterFunc,
  ValueFormatterParams,
} from 'ag-grid-community';
import {
  DFWhole,
  DFColumn,
  ColumnHint,
  ColumnIntegertHint,
  ColumnFloatHint,
  ColumnDatetimeHint,
} from './staticData';
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

export const basicIntFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

export const stringFormatter = (params: ValueFormatterParams): string => {
  const val = params.value;
  return val;
};

const dictDisplayer = (val: Record<string, any>): string => {
  const objBody = _.map(
    val,
    (value, key) => `'${key}': ${objDisplayer(value)}`
  ).join(',');
  return `{ ${objBody} }`;
};

export const isValidDate = (possibleDate: any): boolean => {
  if (_.isDate(possibleDate) && isFinite(possibleDate.getTime())) {
    return true;
  }
  return false;
};

const DEFAULT_DATE_FORMAT: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: 'numeric',
  minute: 'numeric',
  second: 'numeric',
  hour12: false,
};

export const dateDisplayerDefault = (d: Date): string => {
  const fullStr = d.toLocaleDateString('en-CA', DEFAULT_DATE_FORMAT);
  const [dateStr, timeStr] = fullStr.split(',');
  //const retVal = `${dateStr} ${timeStr.padStart(12)}`;
  const retVal = `${dateStr} ${timeStr}`;
  return retVal;
};

export const getDatetimeFormatter = (colHint: ColumnDatetimeHint) => {
  return (params: ValueFormatterParams): string => {
    // console.log("params", params)
    const val = params.value;
    if (val === null || val === undefined) {
      return '';
    }
    const d = new Date(val);
    if (!isValidDate(d)) {
      return '';
    }
    if (colHint.formatter === 'default') {
      return dateDisplayerDefault(d);
    } else if (colHint.formatter === 'toLocaleString') {
      return d.toLocaleDateString(colHint.locale, colHint.args);
    }
    throw new Error('unreachable code in getDatetimeFormatter');
  };
};

const objDisplayer = (val: any | any[]): string => {
  if (val === undefined || val === null) {
    return 'None';
  } else if (_.isArray(val)) {
    return `[ ${val.map(objDisplayer).join(', ')}]`;
  } else if (_.isBoolean(val)) {
    return boolDisplayer(val);
  } else if (_.isObject(val)) {
    return dictDisplayer(val);
  } else {
    return val.toString();
  }
  return val;
};

const objFormatter = (params: ValueFormatterParams): string => {
  const val = params.value;
  return objDisplayer(val);
};

export const boolDisplayer = (val: boolean) => {
  if (val === true) {
    return 'True';
  } else if (val === false) {
    return 'False';
  }
  return '';
};

export const booleanFormatter = (params: ValueFormatterParams): string => {
  const val = params.value;
  return boolDisplayer(val);
};

const getIntegerFormatter = (hint: ColumnIntegertHint) => {
  const commas = Math.floor(hint.max_digits / 3);
  const totalWidth = commas + hint.max_digits;

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

const getFloatFormatter = (hint: ColumnFloatHint) => {
  const floatFormatter = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
  return (params: ValueFormatterParams): string => {
    if (params.value === null) {
      return '';
    }
    return floatFormatter.format(params.value);
  };
};

function getFormatter(hint: ColumnHint): ValueFormatterFunc<unknown> {
  if (hint === undefined) {
    return stringFormatter;
  }
  if (hint.type === 'integer') {
    return getIntegerFormatter(hint);
  } else if (hint.type === 'string') {
    return stringFormatter;
  } else if (hint.type === 'datetime') {
    return getDatetimeFormatter(hint);
  } else if (hint.type === 'float') {
    return getFloatFormatter(hint);
  } else if (hint.type === 'boolean') {
    return booleanFormatter;
  } else if (hint.type === 'obj') {
    return objFormatter;
  }
  return stringFormatter;
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
        _.get(tdf.table_hints, f.name, { is_numeric: false, type: 'obj' })
      ),
    };
    if (f.name === 'index') {
      colDef.pinned = 'left';
    }
    return colDef;
  });
  return [retColumns, tdf.data];
}
