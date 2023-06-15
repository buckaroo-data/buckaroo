import { ColDef, ValueFormatterFunc, ValueFormatterParams } from 'ag-grid-community';
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

export const intFormatter = new Intl.NumberFormat(
  'en-US', { minimumFractionDigits:0, maximumFractionDigits: 3 });

const floatFormatter = new Intl.NumberFormat('en-US', { minimumFractionDigits:3, maximumFractionDigits: 3 });

export const anyFormatter = (params: ValueFormatterParams):string => {
  const val = params.value;
  try {
    const num = Number(val)
    if (val === null) {
      return "";
    } else if (val === undefined) {
      return "";
    }
    else if (Number.isFinite(num)) {
      if (Number.isInteger(num)) {
	const formatted = intFormatter.format(num)
	return `${formatted}    `
      } else {
	return floatFormatter.format(num)
      }
    }
  } catch (e:any) {
    //console.log("formatting error", val, e);
  }
  return val
}
/*
  console.log((new Intl.NumberFormat('en-US')).format(amount))
  console.log((new Intl.NumberFormat('en-US', {  maximumFractionDigits: 1})).format(number))

  console.log(`|${last4Digits.padStart(7, ' ')}|`)
  
 valueFormatter: currencyFormatter}
    ];
    
    function currencyFormatter(params) {
        return '£' + formatNumber(params.value);
    }
*/
function getFormatter(hint: ColumnHint):  ValueFormatterFunc<unknown> {
  if (hint === undefined || hint.is_numeric === false) {
    return anyFormatter;
  } else {
    const commas = Math.floor(hint.max_digits / 3);

    if (hint.is_integer) {
      const totalWidth = commas + hint.max_digits;
      return (params: ValueFormatterParams):string => {
        console.log("params", params)

        const formatter = new Intl.NumberFormat('en-US');
        return formatter.format(params.value).padStart(totalWidth, ' ');
      };
    } else {
      /*

      const intWidth = commas + hint.max_digits;
      const fracWidth = 4;
      return (params: ValueFormatterParams):string => {
        console.log("params", params)
        const formatter = new Intl.NumberFormat('en-US', {  maximumFractionDigits: 3 });
        //console.log(`|${last4Digits.padStart(7, ' ')}|`)
        const numFormatted = formatter.format(params.value);
        if(numFormatted.includes(".")){
          const [intPart, fracPart] = numFormatted.split(".")
          return [intPart.padStart(intWidth, " "), fracPart.padEnd(3, " ")].join(".") }
        else {
          return numFormatted.padStart(intWidth, " ").padEnd(intWidth + fracWidth, " ")
        }
      };*/
      return (params: ValueFormatterParams):string => {
        //console.log("params", params)

        return floatFormatter.format(params.value);
      };

    }
  }
}

export function dfToAgrid(tdf: DFWhole): [ColDef[], unknown[]] {
  const fields = tdf.schema.fields;
  //console.log("tdf", tdf);
  //console.log("hints", tdf.table_hints);
  const retColumns:ColDef[] = fields.map((f: DFColumn) => {
    //console.log(f.name, tdf.table_hints[f.name])
    const colDef:ColDef = {field: f.name, valueFormatter:getFormatter(_.get(tdf.table_hints,f.name, { is_numeric:false})) }
    if (f.name === 'index') {
      colDef.pinned = 'left';
    }
		return colDef;
  });
  return [retColumns, tdf.data];
}
