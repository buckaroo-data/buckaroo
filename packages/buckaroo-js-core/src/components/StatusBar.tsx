// https://plnkr.co/edit/QTNwBb2VEn81lf4t?open=index.tsx
import React, { useRef, useCallback } from "react";
import _ from "lodash";
import { AgGridReact } from "@ag-grid-community/react"; // the AG Grid React Component
import { ColDef, GridOptions } from "@ag-grid-community/core";
import { basicIntFormatter } from "./DFViewerParts/Displayer";
import { DFMeta } from "./WidgetTypes";
import { BuckarooOptions } from "./WidgetTypes";
import { BuckarooState, BKeys } from "./WidgetTypes";
export type setColumFunc = (newCol: string) => void;

const helpCell = function (_params: any) {
    return (
        <a
            href="https://buckaroo-data.readthedocs.io/en/latest/feature_reference.html"
            target="_blank"
            rel="noopener noreferrer"
        >
            ?
        </a>
    );
};

export function StatusBar({
    dfMeta,
    buckarooState,
    setBuckarooState,
    buckarooOptions,
}: {
    dfMeta: DFMeta;
    buckarooState: BuckarooState;
    setBuckarooState: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckarooOptions: BuckarooOptions;
}) {
    const optionCycles = buckarooOptions;

    const idxs = _.fromPairs(
        _.map(_.keys(optionCycles), (k) => [
            k,
            _.indexOf(optionCycles[k as BKeys], buckarooState[k as BKeys]),
        ]),
    );

    const nextIndex = (curIdx: number, arr: any[]) => {
        if (curIdx === arr.length - 1) {
            return 0;
        }
        return curIdx + 1;
    };

    const newBuckarooState = (k: BKeys) => {
        const arr = optionCycles[k];
        const curIdx = idxs[k];
        const nextIdx = nextIndex(curIdx, arr);
        const newVal = arr[nextIdx];
        const newState = _.clone(buckarooState);
        newState[k] = newVal;
        return newState;
    };

    const excludeKeys = ["quick_command_args", "search", "show_displayed_rows"];
    const updateDict = (event: any) => {
        const colName = event.column.getColId();
        if (_.includes(excludeKeys, colName)) {
            return;
        }
        if (_.includes(_.keys(buckarooState), colName)) {
            const nbstate = newBuckarooState(colName as BKeys);
            setBuckarooState(nbstate);
        }
    };

    const handleCellChange = useCallback((params: { oldValue: any; newValue: any }) => {
        const { oldValue, newValue } = params;

        if (oldValue !== newValue && newValue !== null) {
            //console.log('Edited cell:', newValue);
            const newState = {
                ...buckarooState,
                quick_command_args: { search: [newValue] },
            };
            //console.log('handleCellChange', buckarooState, newState);
            setBuckarooState(newState);
        }
    }, []);

    const columnDefs: ColDef[] = [
        {
            field: "search",
            headerName: "search",
            width: 200,
            editable: true,
            onCellValueChanged: handleCellChange,
            //hide: !showSearch,
        },
        {
            field: "df_display",
            headerName: "Σ", //note the greek symbols instead of icons which require buildchain work
            headerTooltip: "Summary Stats",
            width: 120,
        },
        /*
    {
      field: 'auto_clean',
      //headerName: 'Σ', //note the greek symbols instead of icons which require buildchain work
      headerName: 'auto cleaning',
      headerTooltip: 'Auto Cleaning config',
      width: 120,
    },
    */
        {
            field: "post_processing",
            //      headerName: "Θ",
            headerName: "post processing",
            headerTooltip: "post process method",
            width: 100,
        },
        {
            field: "show_commands",
            headerName: "λ",
            headerTooltip: "Show Commands",
            width: 30,
        },

        { field: "sampled", headerName: "Ξ", headerTooltip: "Sampled", width: 30 },
        {
            field: "help",
            headerName: "?",
            headerTooltip: "Help",
            width: 30,
            cellRenderer: helpCell,
        },
        { field: "total_rows", width: 100 },
        { field: "filtered_rows", headerName: "filtered", width: 85 },
        {
            field: "rows_shown",
            headerName: "displayed",
            width: 85,
            hide: dfMeta.rows_shown === -1,
        },
        { field: "columns", width: 75 },
    ];

    const searchArg = buckarooState.quick_command_args?.search;
    const searchStr = searchArg && searchArg.length === 1 ? searchArg[0] : "";

    const rowData = [
        {
            total_rows: basicIntFormatter.format(dfMeta.total_rows),
            columns: dfMeta.columns,
            rows_shown: basicIntFormatter.format(dfMeta.rows_shown),
            sampled: buckarooState.sampled || "0",
            auto_clean: buckarooState.auto_clean || "0",
            df_display: buckarooState.df_display,
            filtered_rows: basicIntFormatter.format(dfMeta.filtered_rows),
            post_processing: buckarooState.post_processing,
            show_commands: buckarooState.show_commands || "0",
            search: searchStr,
        },
    ];

    const gridOptions: GridOptions = {
        suppressRowClickSelection: true,
    };

    const gridRef = useRef<AgGridReact<unknown>>(null);
    const defaultColDef = {
        cellStyle: { textAlign: "left" },
    };
    return (
        <div className="statusBar">
            <div style={{ height: 50 }} className="theme-hanger ag-theme-alpine-dark">
                <AgGridReact
                    ref={gridRef}
                    onCellClicked={updateDict}
                    gridOptions={gridOptions}
                    defaultColDef={defaultColDef}
                    rowData={rowData}
                    columnDefs={columnDefs}
                ></AgGridReact>
            </div>
        </div>
    );
}
