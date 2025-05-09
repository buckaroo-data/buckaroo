import {
    CellClassParams,
} from "@ag-grid-community/core";

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
    const L = histogram_edges.length
    if (L === 0) {
        return 0;
    }
    
    // this is n^2 for number of histogram edges, but histogram edges should be about 10
    
    for (let i = 0; i < histogram_edges.length; i++) {
        if (val <= histogram_edges[i]) {
            return i;
        }
    }
    if (val > histogram_edges[L-1]) {
        return L-1
    }
    return histogram_edges.length;
}

export function colorMap(cmr: ColorMapRules) {
    // https://colorcet.com/gallery.html#isoluminant
    // https://github.com/holoviz/colorcet/tree/main/assets/CET
    // https://github.com/bokeh/bokeh/blob/ed285b11ab196e72336b47bf12f44e1bef5abed3/src/bokeh/models/mappers.py#L304


    function cellStyle(params: CellClassParams) {
        const cmap = getColorMap(cmr.map_name);
        const baseReturn = {backgroundColor:"inherit"};

        const summarys = params.context?.histogram_stats;
        const statsCol = cmr.val_column; // || col_name;
        if (statsCol ===  undefined || summarys === undefined){
            console.log("66 couldn't find stats_col")
            return baseReturn;
        } 
        const summary_stats_cell = summarys[statsCol];
        if (summary_stats_cell === undefined || summary_stats_cell.histogram_bins === undefined ) {
            console.log("69 couldn't find summary_stats");
            return baseReturn
        }
        const histogram_edges = summary_stats_cell.histogram_bins;


        function numberToColor(val: number) {
            const histoIndex = getHistoIndex(val, histogram_edges);
            const scaledIndex = Math.round((histoIndex / histogram_edges.length) * cmap.length);
            return cmap[scaledIndex];
        }
        const val = (cmr.val_column && params.data) ? params.data[cmr.val_column] : params.value;
        const dataColor = numberToColor(val);
	    const isPinned = params.node.rowPinned;
        const color = isPinned? "inherit": dataColor;

        return {
            backgroundColor: color,
        };
    }
    return {
        cellStyle: cellStyle,
    };
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
    return {
        cellStyle: cellStyle,
    };
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
    return {
        cellStyle: cellStyle,
    };
}

export function getStyler(cmr: ColorMappingConfig) {
    switch (cmr.color_rule) {
        case "color_map": return colorMap(cmr);
        case "color_categorical": return categoricalColor(cmr);
        case "color_from_column": return colorFromColumn(cmr);
        case "color_not_null":    return colorNotNull(cmr);
        }
}
