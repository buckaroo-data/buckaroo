// https://plnkr.co/edit/QTNwBb2VEn81lf4t?open=index.tsx
import React, { useRef, useCallback, useState, memo, useEffect, useMemo } from "react";
import * as _ from "lodash-es";
import { AgGridReact } from "ag-grid-react"; // the AG Grid React Component
import { ColDef, GridApi, GridOptions } from "ag-grid-community";
import { basicIntFormatter } from "./DFViewerParts/Displayer";
import { DFMeta } from "./WidgetTypes";
import { BuckarooOptions } from "./WidgetTypes";
import { BuckarooState, BKeys } from "./WidgetTypes";
import { CustomCellEditorProps } from 'ag-grid-react';
import { getThemeForScheme, resolveColorScheme, resolveThemeColors } from "./DFViewerParts/gridUtils";
import type { ThemeConfig } from "./DFViewerParts/gridUtils";
import { Theme } from "ag-grid-community";
import { useColorScheme } from "./useColorScheme";

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

const dfDisplayCell = function (params: any) {
    const value = params.value;
    const options = params.context.buckarooOptions.df_display;
    
    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const newState = _.clone(params.context.buckarooState);
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
        const newState = _.clone(params.context.buckarooState);
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
        const newState = _.clone(params.context.buckarooState);
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
        const newState = _.clone(params.context.buckarooState);
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

// Debounce delay for live search. 300ms is above the typical inter-keystroke
// pause (~150ms) so it doesn't fire mid-word, but well below the "feels slow"
// threshold. Server-side filter cost on a ~900k-row df is ~80-230ms.
const SEARCH_DEBOUNCE_MS = 300;

// Wall-clock HH:MM:SS.mmm for [bk-flash …] correlation with the rest of the
// search-flow timeline (BuckarooWidgetInfinite, DFViewerInfinite, Python).
// Same opt-in gate, dynamic — flip `globalThis.__BK_FLASH__ = true` in
// DevTools at any time to enable.
const bkTs = (): string => {
    const d = new Date();
    const p2 = (n: number) => String(n).padStart(2, "0");
    const p3 = (n: number) => String(n).padStart(3, "0");
    return `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}.${p3(d.getMilliseconds())}`;
};
const bkFlashOn = (): boolean =>
    typeof globalThis !== "undefined" && (globalThis as { __BK_FLASH__?: boolean }).__BK_FLASH__ === true;
const bkSearchLog = (event: string): void => {
    if (!bkFlashOn()) return;
    // eslint-disable-next-line no-console
    console.log(`[bk-flash ${bkTs()}] ${event}`);
};
const describe = (el: Element | null): string => {
    if (!el) return "null";
    const tag = el.tagName.toLowerCase();
    const cls = (el.getAttribute("class") || "").split(/\s+/).filter(Boolean).slice(0, 2).join(".");
    const role = el.getAttribute("role");
    const colid = (el as HTMLElement).getAttribute("col-id");
    const parts = [tag];
    if (cls) parts.push(`.${cls}`);
    if (role) parts.push(`[role=${role}]`);
    if (colid) parts.push(`[col-id=${colid}]`);
    return parts.join("");
};
let _fsc_instance_seq = 0;
// AG-Grid destroys and recreates the cellRenderer instance on every
// onCellValueChanged (the status-bar grid regenerates row data on each
// buckarooState change). Component-scoped useRef is wiped each remount, so
// we hoist engagement state to module scope. Same browser tab can only show
// one BuckarooWidget search at a time in practice, so a single shared
// timestamp is fine.
let _fsc_engagedAt = 0;          // ms timestamp of last user typing/focus
let _fsc_carryoverCaret = 0;     // selection caret from the dying instance,
                                 // so the new instance can restore it
const _FSC_REFOCUS_WINDOW_MS = 5000;

export const fakeSearchCell = function (_params: any) {
    const value = _params.value;

    const [searchVal, setSearchVal] = useState<string>(value||'');
    const inputRef = useRef<HTMLInputElement>(null);
    const instIdRef = useRef<number | null>(null);
    if (instIdRef.current === null) instIdRef.current = ++_fsc_instance_seq;
    const iid = instIdRef.current;

    // Component mount / unmount. On mount, if the user was recently typing
    // into the search box (any previous instance), restore focus to this
    // new input. setTimeout defers past AG-Grid's remount finalization;
    // rAF is the backup.
    useEffect(() => {
        const recentlyEngaged = Date.now() - _fsc_engagedAt < _FSC_REFOCUS_WINDOW_MS;
        bkSearchLog(`fakeSearchCell MOUNT  iid=${iid}  value="${value || ""}"  recentlyEngaged=${recentlyEngaged}`);
        if (recentlyEngaged) {
            const refocus = (stage: string) => {
                if (document.activeElement !== inputRef.current) {
                    inputRef.current?.focus();
                    if (inputRef.current && _fsc_carryoverCaret >= 0) {
                        const len = inputRef.current.value.length;
                        const pos = Math.min(_fsc_carryoverCaret, len);
                        try { inputRef.current.setSelectionRange(pos, pos); } catch { /* ignore */ }
                    }
                }
                bkSearchLog(`mount-refocus ${stage}  iid=${iid}  after=${describe(document.activeElement)}  matches=${document.activeElement === inputRef.current}`);
            };
            setTimeout(() => refocus("setTimeout(0)"), 0);
            requestAnimationFrame(() => refocus("rAF"));
        }
        return () => {
            // Capture caret before AG-Grid tears down the input.
            if (inputRef.current && document.activeElement === inputRef.current) {
                _fsc_carryoverCaret = inputRef.current.selectionStart ?? inputRef.current.value.length;
            }
            bkSearchLog(`fakeSearchCell UNMOUNT iid=${iid}  carryoverCaret=${_fsc_carryoverCaret}`);
        };
    }, []);

    const submit = (v: string) => {
        _params.setValue(v === '' ? null : v)
    }

    // Live search: after SEARCH_DEBOUNCE_MS of no keystrokes, push the term
    // upstream. Buttons / Enter bypass the debounce and fire immediately.
    useEffect(() => {
        if (searchVal === (value || '')) return;  // initial mount, no-op
        const t = setTimeout(() => submit(searchVal), SEARCH_DEBOUNCE_MS);
        return () => clearTimeout(t);
    }, [searchVal, value]);

    const keyPressHandler = (event:React.KeyboardEvent<HTMLInputElement> ) => {
        if (event.key === "Enter") {
            event.preventDefault();
            submit(searchVal);
        }
    }
    return (
        <div
            className={"FakeSearchEditor"}
            tabIndex={1} // important - without this the key presses wont be caught
            style={{ display: "flex", flexDirection: "row", width: "100%" }}
        >
            <input
                ref={inputRef}
                type="text"
                style={{ flex: "1 1 auto", minWidth: 0 }}
                value={searchVal}
                onFocus={() => {
                    _fsc_engagedAt = Date.now();
                    bkSearchLog(`input onFocus  iid=${iid}`);
                }}
                onChange={({ target: { value }}) => { _fsc_engagedAt = Date.now(); setSearchVal(value); }}
                onBlur={(e) => {
                    const next = e.relatedTarget as HTMLElement | null;
                    const inside = next && e.currentTarget.parentElement?.contains(next);
                    bkSearchLog(`input onBlur  iid=${iid}  relatedTarget=${describe(next)}  insideSearchCell=${!!inside}`);
                    // Only un-engage when the user intentionally clicked
                    // outside the search cell. AG-Grid's remount-driven blur
                    // (relatedTarget === null, AG-Grid tearing the input out
                    // from under us) does NOT un-engage — that's the whole
                    // point of the module-level engagedAt.
                    if (next && !inside) {
                        _fsc_engagedAt = 0;
                    }
                }}
                onSubmit={() => submit(searchVal)}
                onKeyDown={keyPressHandler}
            />
            <button style={{ flex: "none" }} onClick={() => submit(searchVal)}>&#x1F50D;</button>
            <button style={{ flex: "none" }}
                    onClick={() => {
                        setSearchVal('');
                        _params.setValue('');
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
    heightOverride,
    themeConfig
}: {
    dfMeta: DFMeta;
    buckarooState: BuckarooState;
    setBuckarooState: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckarooOptions: BuckarooOptions;
    heightOverride?: number;
    themeConfig?: ThemeConfig;
}) {
    if (false) {
	console.log("heightOverride", heightOverride);
    }
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
        console.log("event.column", event.column, event.column.getColId());
        const colName = event.column.getColId();
        if (_.includes(excludeKeys, colName)) {
            return;
        }
        if (_.includes(_.keys(buckarooState), colName)) {
            const nbstate = newBuckarooState(colName as BKeys);
            setBuckarooState(nbstate);
        }
    };

    const handleSearchCellChange = useCallback((params: { oldValue: any; newValue: any }) => {
        const { oldValue, newValue } = params;
        if (oldValue !== newValue && newValue !== null) {
            bkSearchLog(`search term set → buckarooState.quick_command_args.search  oldValue="${oldValue ?? ""}"  newValue="${newValue}"`);
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
            id: "statusbar",  // stable id consumed by getRowId below
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
        // Stable row identity. Without this, every parent re-render (every
        // buckarooState change) gives AG-Grid a fresh rowData array literal
        // with no way to recognize "this is the same row" — so it destroys
        // and recreates every cellRenderer instance, blowing away the
        // search input's focus, selection, and any in-flight typing. With
        // getRowId pinned, AG-Grid passes new props to the existing
        // cellRenderer instances instead.
        getRowId: () => "statusbar",
    };

    const gridRef = useRef<AgGridReact<unknown>>(null);

    const onGridReady = useCallback((params: {api:GridApi}) => {
        console.log("StatusBar252 onGridReady statusbar", params)
    }, []);

    const defaultColDef = {
        sortable:false,
        cellStyle: { textAlign: "left" },
    };

    const osColorScheme = useColorScheme();
    const effectiveScheme = resolveColorScheme(osColorScheme, themeConfig);
    const resolvedTheme = resolveThemeColors(effectiveScheme, themeConfig);
    const statusTheme: Theme = useMemo(()=> getThemeForScheme(effectiveScheme, resolvedTheme).withParams({
        headerFontSize: 14,
        rowVerticalPaddingScale: 0.8,
    }), [effectiveScheme, resolvedTheme]);
    const themeClass = effectiveScheme === 'light' ? 'ag-theme-alpine' : 'ag-theme-alpine-dark';
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
