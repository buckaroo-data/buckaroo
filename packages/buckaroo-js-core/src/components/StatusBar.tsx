// https://plnkr.co/edit/QTNwBb2VEn81lf4t?open=index.tsx
import React, { useRef, useCallback, useState, memo, useEffect, useMemo } from "react";
import { clone, fromPairs, includes, indexOf, keys, map } from "lodash-es";
import { AgGridReact } from "@ag-grid-community/react"; // the AG Grid React Component
import { ColDef, GridApi, GridOptions, ModuleRegistry } from "@ag-grid-community/core";
import { basicIntFormatter } from "./DFViewerParts/Displayer";
import { DFMeta } from "./WidgetTypes";
import { BuckarooOptions } from "./WidgetTypes";
import { BuckarooState, BKeys } from "./WidgetTypes";
import { ClientSideRowModelModule } from "@ag-grid-community/client-side-row-model";
import { CustomCellEditorProps } from '@ag-grid-community/react';
import { getThemeForScheme } from "./DFViewerParts/gridUtils";
import { Theme } from "@ag-grid-community/theming";
import { useColorScheme } from "./useColorScheme";

export type setColumFunc = (newCol: string) => void;
ModuleRegistry.registerModules([ClientSideRowModelModule]);
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

const dfDisplayCell = function (params: any) {
    const value = params.value;
    const options = params.context.buckarooOptions.df_display;
    
    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const newState = clone(params.context.buckarooState);
        newState.df_display = event.target.value;
        params.context.setBuckarooState(newState);
    };

    return (
        <select 
            value={value} 
            onChange={handleChange}
            style={{ width: '100%', background: 'transparent', border: 'none', color: 'inherit' }}
        >
            {options.map((option: string) => (
                <option key={option} value={option}>
                    {option}
                </option>
            ))}
        </select>
    );
};

const cleaningMethodCell = function (params: any) {
    const value = params.value;
    const options = params.context.buckarooOptions.cleaning_method;
    
    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const newState = clone(params.context.buckarooState);
        newState.cleaning_method = event.target.value;
        params.context.setBuckarooState(newState);
    };

    return (
        <select 
            value={value} 
            onChange={handleChange}
            style={{ width: '100%', background: 'transparent', border: 'none', color: 'inherit' }}
        >
            {options.map((option: string) => (
                <option key={option} value={option}>
                    {option}
                </option>
            ))}
        </select>
    );
};

const postProcessingCell = function (params: any) {
    const value = params.value;
    const options = params.context.buckarooOptions.post_processing;
    
    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const newState = clone(params.context.buckarooState);
        newState.post_processing = event.target.value;
        params.context.setBuckarooState(newState);
    };

    return (
        <select 
            value={value} 
            onChange={handleChange}
            style={{ width: '100%', background: 'transparent', border: 'none', color: 'inherit' }}
        >
            {options.map((option: string) => (
                <option key={option} value={option}>
                    {option}
                </option>
            ))}
        </select>
    );
};

const showCommandsCell = function (params: any) {
    const value = params.value === "1";
    
    const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const newState = clone(params.context.buckarooState);
        newState.show_commands = event.target.checked ? "1" : "0";
        params.context.setBuckarooState(newState);
    };

    return (
        <input
            type="checkbox"
            checked={value}
            onChange={handleChange}
            style={{ margin: '0 auto', display: 'block' }}
        />
    );
};

export const fakeSearchCell = function (_params: any) {
    const value = _params.value;

    const [searchVal, setSearchVal] = useState<string>(value||'');
    const setVal = () => {
        _params.setValue(searchVal === '' ? null : searchVal)
    }

    const keyPressHandler = (event:React.KeyboardEvent<HTMLInputElement> ) => {
        // If the user presses the "Enter" key on the keyboard
    if (event.key === "Enter") {
      // Cancel the default action, if needed
      event.preventDefault();
      setVal()
      // Trigger the button element with a click
      //document.getElementById("myBtn").click();
    }
  } 
    return (
        <div
            className={"FakeSearchEditor"}
            tabIndex={1} // important - without this the key presses wont be caught
            style={{ display: "flex", flexDirection: "row", width: "100%" }}
        >
            <input
                type="text"
                style={{ flex: "1 1 auto", minWidth: 0 }}
                value={searchVal}
                onChange={({ target: { value }}) => setSearchVal(value)}
                onSubmit={setVal}
                onKeyDown={keyPressHandler}
            />
            <button style={{ flex: "none" }} onClick={setVal}>&#x1F50D;</button>
            <button style={{ flex: "none" }}
                    onClick={(clickParams) => {
                        console.log("clickParams", clickParams)
                        _params.setValue("")
                    }}
            >X</button>
        </div>
    )
}

export const SearchEditor =  memo(({ value, onValueChange, stopEditing }: CustomCellEditorProps) => {
    const [_ready, setReady] = useState(false);
    const refContainer = useRef<HTMLDivElement>(null);


    useEffect(() => {
        refContainer.current?.focus();
        setReady(true);
    }, []);


    return (
        <div
            className={"SearchEditor"}
            ref={refContainer}
            tabIndex={1} // important - without this the key presses wont be caught
            style={{display:"flex", "flexDirection":"row"}}
        >
       <input
           type="text"
           style={{flex:"auto", width:150}}
           value={value || ''}
           onChange={({ target: { value }}) => onValueChange(value === '' ? null : value)}
       />
       <button style={{flex:"none"}}
                onClick={() => {onValueChange(""),
                    stopEditing();
                }}
       >X</button>
        </div>
    );
});

export function StatusBar({
    dfMeta,
    buckarooState,
    setBuckarooState,
    buckarooOptions,
    heightOverride
}: {
    dfMeta: DFMeta;
    buckarooState: BuckarooState;
    setBuckarooState: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckarooOptions: BuckarooOptions;
    heightOverride?: number;
}) {
    if (false) {
	console.log("heightOverride", heightOverride);
    }
    const optionCycles = buckarooOptions;
    const idxs = fromPairs(
        map(keys(optionCycles), (k) => [
            k,
            indexOf(optionCycles[k as BKeys], buckarooState[k as BKeys]),
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
        const newState = clone(buckarooState);
        newState[k] = newVal;
        return newState;
    };

    const excludeKeys = ["quick_command_args", "search", "show_displayed_rows"];
    const updateDict = (event: any) => {
        console.log("event.column", event.column, event.column.getColId());
        const colName = event.column.getColId();
        if (includes(excludeKeys, colName)) {
            return;
        }
        if (includes(keys(buckarooState), colName)) {
            const nbstate = newBuckarooState(colName as BKeys);
            setBuckarooState(nbstate);
        }
    };

    const handleSearchCellChange = useCallback((params: { oldValue: any; newValue: any }) => {
        const { oldValue, newValue } = params;
        if (oldValue !== newValue && newValue !== null) {
            //console.log('Edited cell:', newValue);
            const newState = {
                ...buckarooState,
                quick_command_args: { search: [newValue] },
            };

            setBuckarooState(newState);
        }
    }, []);

    const columnDefs: ColDef[] = [
        {
            field: "search",
            headerName: "search",
            width: 200,
            //editable: true,
            cellEditor: SearchEditor,
            cellRenderer: fakeSearchCell,

            onCellValueChanged: handleSearchCellChange,
        },

        {
            field: "df_display",
            headerName: "Σ", //note the greek symbols instead of icons which require buildchain work
            headerTooltip: "Summary Stats",
            width: 120,
            cellRenderer: dfDisplayCell,
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
            headerName: "post processing",
            headerTooltip: "post process method",
            width: 100,
            cellRenderer: postProcessingCell,
        },
        {
            field: "show_commands",
            headerName: "λ",
            headerTooltip: "Show Commands",
            width: 30,
            cellRenderer: showCommandsCell,
        },
        { 
            field: "cleaning_method", 
            headerName: "cleaning", 
            headerTooltip: "Auto cleaning method", 
            width: 80,
            cellRenderer: cleaningMethodCell,
        },
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
            //sampled: buckarooState.sampled || "0",
            cleaning_method: buckarooState.cleaning_method || "0",
            df_display: buckarooState.df_display,
            filtered_rows: basicIntFormatter.format(dfMeta.filtered_rows),
            post_processing: buckarooState.post_processing,
            show_commands: buckarooState.show_commands || "0",
            search: searchStr
        },
    ];

    const gridOptions: GridOptions = {
        suppressRowClickSelection: true,
    };

    const gridRef = useRef<AgGridReact<unknown>>(null);

    const onGridReady = useCallback((params: {api:GridApi}) => {
        console.log("StatusBar252 onGridReady statusbar", params)
    }, []);

    const defaultColDef = {
        sortable:false,
        cellStyle: { textAlign: "left" },
    };

    const colorScheme = useColorScheme();
    const statusTheme: Theme = useMemo(()=> getThemeForScheme(colorScheme).withParams({
        headerFontSize: 14,
        rowVerticalPaddingScale: 0.8,
    }), [colorScheme]);
    const themeClass = colorScheme === 'light' ? 'ag-theme-alpine' : 'ag-theme-alpine-dark';
    return (
        <div className="status-bar">
            <div
            className={`theme-hanger ${themeClass}`}>
                <AgGridReact
                    ref={gridRef}
                    theme={statusTheme}
                    loadThemeGoogleFonts
                    onCellEditingStopped={onGridReady}
                    onColumnHeaderClicked={updateDict}
                    onGridReady={onGridReady}
                    gridOptions={gridOptions}
                    defaultColDef={defaultColDef}
                    rowData={rowData}
                    domLayout={"autoHeight"}
                    columnDefs={columnDefs}
                    context={{
                        buckarooState,
                        setBuckarooState,
                        buckarooOptions
                    }}
                ></AgGridReact>
            </div>
        </div>
    );
}
