import { ColumnConfig, DFViewerConfig } from "./DFWhole";

export const objColumn = (col_name: string): ColumnConfig => ({
  col_name,
  displayer_args: {
    displayer: 'obj' as const,
  },
});

export const floatColumn = (col_name: string, min_fraction_digits: number, max_fraction_digits: number): ColumnConfig => ({
  col_name,
  displayer_args: {
    displayer: 'float' as const,
    min_fraction_digits,
    max_fraction_digits,
  },
});

export const integerColumn = (col_name: string, min_digits: number, max_digits: number): ColumnConfig => ({
  col_name,
  displayer_args: {
    displayer: 'integer' as const,
    min_digits,
    max_digits,
  },
});

export const primaryConfigPrimary: DFViewerConfig = {
  column_config: [
    floatColumn('a', 2, 8),
    integerColumn('a', 2, 3),
    objColumn('b'),
    {
      col_name: 'b',
      displayer_args: {
        displayer: 'string',
      },
    },
  ],
  pinned_rows: [],
}; 