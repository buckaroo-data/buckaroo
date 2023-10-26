import {
  ColDef,
  ValueFormatterFunc,
  ValueFormatterParams,
} from 'ag-grid-community';
import { DFWhole, DFColumn, ColumnHint, ColumnIntegertHint, ColumnFloatHint } from './staticData';
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


export const basicIntFormatter  = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

export const stringFormatter = (params: ValueFormatterParams): string => {
  const val = params.value;
  return val;
};


export const booleanFormatter = (params: ValueFormatterParams): string => {
  const val = params.value;
  if (val === true) {
    return "True"
  } else if (val === false) {
    return "False"
  }
  return ""
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
}

function getFormatter(hint: ColumnHint): ValueFormatterFunc<unknown> {
  if (hint === undefined) {
    return stringFormatter;
  }
  if (hint.type === "integer") {
    return getIntegerFormatter(hint);
  }
  else if (hint.type === "string") {
      return stringFormatter;
    
  } else if (hint.type === "float") {
    return getFloatFormatter(hint);
  } else if (hint.type === "boolean") {
    return booleanFormatter;
  } else if (hint.type === "obj") {
    return stringFormatter;
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
        _.get(tdf.table_hints, f.name, { is_numeric: false, type:"obj" })
      ),
    };
    if (f.name === 'index') {
      colDef.pinned = 'left';
    }
    return colDef;
  });
  return [retColumns, tdf.data];
}
