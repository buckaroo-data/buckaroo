import { ColDef } from 'ag-grid-community';
import { DFWhole, DFColumn } from './staticData';

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

export function dfToAgrid(tdf: DFWhole): [ColDef[], unknown[]] {
  const fields = tdf.schema.fields;
  const retColumns = fields.map((f: DFColumn) => {
    return { field: f.name };
  });
  return [retColumns, tdf.data];
}
