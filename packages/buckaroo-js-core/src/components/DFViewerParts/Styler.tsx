import {
    CellClassParams,
} from "@ag-grid-community/core";
import { SDFT } from "./DFWhole";

import { BLUE_TO_YELLOW, DIVERGING_RED_WHITE_BLUE } from "../../baked_data/colorMap";
import {
    ColorMappingConfig,
    ColorMapRules,
    ColorCategoricalRules,
    ColorWhenNotNullRules,
    ColorFromColumn,
    ColorMap
} from "./DFWhole";

const getColorMap =  (cm:ColorMap): string[] => {
    if (cm === "BLUE_TO_YELLOW") {
	return BLUE_TO_YELLOW
    } else if (cm === "DIVERGING_RED_WHITE_BLUE") {
	return DIVERGING_RED_WHITE_BLUE
    } else {
	return cm
    }
}

export function getHistoIndex(val: number, histogram_edges: number[]): number {
    /*
np.histogram([1, 2, 3, 4,  10, 20, 30, 40, 300, 300, 400, 500], bins=5)
( [  8,       0,     2,     1,     1], 
[  1. , 100.8, 200.6, 300.4, 400.2, 500. ])
The bottom matters for us, those are the endge

this means that 8 values are between 1 and 100.8  and 2 values are between 200.6 and 300.4
  */
    if (histogram_edges.length === 0) {
        return 0;
    }
    for (let i = 0; i < histogram_edges.length; i++) {
        if (val <= histogram_edges[i]) {
            return i;
        }
    }
    return histogram_edges.length;
}

export function colorMap(cmr: ColorMapRules, histogram_edges: number[]) {
    // https://colorcet.com/gallery.html#isoluminant
    // https://github.com/holoviz/colorcet/tree/main/assets/CET
    // https://github.com/bokeh/bokeh/blob/ed285b11ab196e72336b47bf12f44e1bef5abed3/src/bokeh/models/mappers.py#L304
    const cmap = getColorMap(cmr.map_name);

    function numberToColor(val: number) {
        const histoIndex = getHistoIndex(val, histogram_edges);
        const scaledIndex = Math.round((histoIndex / histogram_edges.length) * cmap.length);
        return cmap[scaledIndex];
    }

    function cellStyle(params: CellClassParams) {
        const val = (cmr.val_column && params.data) ? params.data[cmr.val_column] : params.value;
        const dataColor = numberToColor(val);
	const isPinned = params.node.rowPinned;
        const color = isPinned? "inherit": dataColor;

        return {
            backgroundColor: color,
        };
    }

    const retProps = {
        cellStyle: cellStyle,
    };
    return retProps;
}

export function categoricalColor(cmr: ColorCategoricalRules) {
    // unlike colorMap, which depends on the histogram,  this indexes directly into the colormap
    // useful for stable coloring based on a number of variables
    const cmap = getColorMap(cmr.map_name);

    function cellStyle(params: CellClassParams) {
        const val = (cmr.val_column && params.data) ? params.data[cmr.val_column] : params.value;
	const isPinned = params.node.rowPinned;
        const color = isPinned? "inherit": cmap[val]

        return {
            backgroundColor: color,
        };
    }

    const retProps = {
        cellStyle: cellStyle,
    };
    return retProps;
}

export function colorNotNull(cmr: ColorWhenNotNullRules) {

    function cellStyle(params: CellClassParams) {
         if (params.data === undefined) {
             return { backgroundColor: "inherit" };
         }
        const val = params.data[cmr.exist_column];
        const valPresent = val && val !== null;
        const isPinned = params.node.rowPinned;
        const color = valPresent && !isPinned ? cmr.conditional_color : "inherit";
         return {
            backgroundColor: color,
         };
    }
    const retProps = {
        cellStyle: cellStyle,
    };
    return retProps;
}    
    

export function colorFromColumn(cmr: ColorFromColumn) {
    function cellStyle(params: CellClassParams) {
        if (params.data === undefined) {
            return { backgroundColor: "inherit" };
        }
        const dataColor = params.data[cmr.val_column];
	const isPinned = params.node.rowPinned;
        const color = dataColor && !isPinned ? dataColor : "inherit";
        return {
            backgroundColor: color
        };
    }

    const retProps = {
        cellStyle: cellStyle,
    };
    return retProps;
}

export function getStyler(cmr: ColorMappingConfig, col_name: string, histogram_stats: SDFT) {
    switch (cmr.color_rule) {
        case "color_map": {
            //block necessary because you cant define varaibles in case blocks
            const statsCol = cmr.val_column || col_name;
            const summary_stats_cell = histogram_stats[statsCol];

            if (summary_stats_cell && summary_stats_cell.histogram_bins !== undefined) {
                return colorMap(cmr, summary_stats_cell.histogram_bins);
            } else {
                console.log("histogram bins not found for color_map");
                return {};
            }
        }
        case "color_categorical": {
            //block necessary because you cant define varaibles in case blocks
	    return categoricalColor(cmr);
        }
        case "color_from_column": {
            //block necessary because you cant define varaibles in case blocks
	    return colorFromColumn(cmr)
        }
        case "color_not_null":
            return colorNotNull(cmr);
    }
}
