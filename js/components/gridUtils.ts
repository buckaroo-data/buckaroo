import { ColDef, ValueFormatterFunc, ValueFormatterParams } from 'ag-grid-community';
import { DFWhole, DFColumn, ColumnHint } from './staticData';

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
    return (params: ValueFormatterParams):string => params.value;
  } else {
    const commas = Math.floor(hint.max_digits / 3);

    if (hint.is_integer) {
      const totalWidth = commas + hint.max_digits;
      return (params: ValueFormatterParams):string => {
        console.log("params", params)

        const formatter = new Intl.NumberFormat('en-US');
        //console.log(`|${last4Digits.padStart(7, ' ')}|`)
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
        const formatter = new Intl.NumberFormat('en-US', { minimumFractionDigits:3, maximumFractionDigits: 3 });
        return formatter.format(params.value);
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
    const colDef:ColDef = {field: f.name, valueFormatter:getFormatter(tdf.table_hints[f.name]) }
    if (f.name === 'index') {
      colDef.pinned = 'left';
    }
		return colDef;
  });
  return [retColumns, tdf.data];
}
