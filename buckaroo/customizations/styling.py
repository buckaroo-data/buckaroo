from buckaroo.dataflow.dataflow import StylingAnalysis
from typing import Any
from buckaroo.styling_helpers import obj_, float_, inherit_, pinned_histogram

# Pixel-width estimation constants, calibrated to AG-Grid theme with
# spacing:5, cellHorizontalPaddingScale:0.3, fontSize:12, headerFontSize:14
_CHAR_PX_DATA = 7       # approx width per character in data cells
_CHAR_PX_HEADER = 8     # approx width per character in header
_CELL_PAD = 16          # total horizontal padding inside a cell
_SORT_ICON = 14         # sort indicator + gap in header
_HISTOGRAM_MIN_PX = 100 # minimum width for a histogram pinned row to render usefully
_MIN_COL_PX = 30        # absolute floor


def _formatted_char_count(displayer_args, column_metadata):
    """Estimate the character count of the widest formatted value."""
    d = displayer_args.get('displayer')

    if d == 'float':
        max_val = column_metadata.get('max', 0) or 0
        min_val = column_metadata.get('min', 0) or 0
        max_abs = max(abs(max_val), abs(min_val))
        int_digits = max(1, len(str(int(max_abs)))) if max_abs == max_abs else 1  # nan guard
        commas = (int_digits - 1) // 3
        frac = displayer_args.get('max_fraction_digits', 0)
        decimal = 1 if frac > 0 else 0
        sign = 1 if min_val < 0 else 0
        return int_digits + commas + decimal + frac + sign

    if d == 'integer':
        max_digits = displayer_args.get('max_digits', 4)
        commas = (max_digits - 1) // 3
        return max_digits + commas

    if d == 'compact_number':
        return 5  # e.g. "5.7B"

    if d == 'string':
        return min(displayer_args.get('max_length', 20), 20)

    if d in ('datetimeLocaleString', 'datetimeDefault'):
        return 18  # "12/31/2024, 11:59 PM"

    if d == 'duration':
        return 14  # e.g. "365d 23h 59m 59s"

    return 8  # obj / fallback


def estimate_min_width_px(displayer_args, header_name, column_metadata, has_histogram=False):
    """Compute a per-column minWidth in pixels from content analysis."""
    data_chars = _formatted_char_count(displayer_args, column_metadata)
    data_px = data_chars * _CHAR_PX_DATA + _CELL_PAD

    hdr_chars = len(str(header_name)) if header_name else 1
    header_px = hdr_chars * _CHAR_PX_HEADER + _SORT_ICON + _CELL_PAD

    width = max(data_px, header_px)
    if has_histogram:
        width = max(width, _HISTOGRAM_MIN_PX)
    return max(width, _MIN_COL_PX)


class DefaultMainStyling(StylingAnalysis):
    requires_summary = ["histogram", "is_numeric", "dtype", "_type"]
    pinned_rows = [obj_('dtype'), pinned_histogram()]


    @classmethod
    def style_column(kls, col:str, column_metadata: Any) -> Any:
        #print(col, list(sd.keys()))
        # `_type` is the discriminator for displayer choice. If it's absent
        # (e.g. a transient sd entry contributed by a lowcode op before the
        # summary stats land), fall back to obj rather than KeyError-ing.
        if len(column_metadata.keys()) == 0 or '_type' not in column_metadata:
            return {'col_name':col, 'displayer_args': {'displayer': 'obj'}}

        digits = 3
        t = column_metadata['_type']
        base_config = {'col_name':str(col)}
        if t == 'integer':
            disp = {'displayer': 'float', 'min_fraction_digits':0, 'max_fraction_digits':0}
        elif t == 'float':
            disp = {'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}
        elif t == 'datetime':
            disp = {'displayer': 'datetimeLocaleString','locale': 'en-US',  'args': {}}
        elif t == 'decimal':
            disp = {'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}
        elif t == 'duration':
            disp = {'displayer': 'duration'}
        elif t in ('time', 'categorical', 'period', 'interval'):
            disp = {'displayer': 'string', 'max_length': 35}
            base_config['tooltip_config'] = {'tooltip_type':'simple', 'val_column': str(col)}
        elif t == 'binary':
            disp = {'displayer': 'obj'}
            base_config['tooltip_config'] = {'tooltip_type':'simple', 'val_column': str(col)}
        elif t == 'string':
            disp = {'displayer': 'string', 'max_length': 35}
            base_config['tooltip_config'] = {'tooltip_type':'simple', 'val_column': str(col)}
        else:
            disp = {'displayer': 'obj'}
            base_config['tooltip_config'] = {'tooltip_type':'simple', 'val_column': str(col)}
        # Lowcode ops (e.g. Search) contribute highlight metadata as flat
        # top-level keys on column_metadata; the JS string displayer reads
        # them from displayer_args.
        if disp.get('displayer') == 'string':
            for k in ('highlight_phrase', 'highlight_regex', 'highlight_color'):
                if k in column_metadata:
                    disp[k] = column_metadata[k]
        # init_sd users may pass the same nested shape they'd use in
        # column_config_overrides — e.g. {'comments': {'displayer_args':
        # {'max_length': 2000}}}. Shallow-merge that into disp so init_sd
        # augments (rather than replaces) styling's computed displayer_args
        # AND coexists with op-supplied highlights. Caller wins per-key.
        if isinstance(column_metadata.get('displayer_args'), dict):
            disp.update(column_metadata['displayer_args'])
        base_config['displayer_args'] = disp

        # Compute content-aware minWidth
        header_name = column_metadata.get('orig_col_name', col)
        has_histogram = any(
            pr.get('displayer_args', {}).get('displayer') == 'histogram'
            for pr in kls.pinned_rows)
        min_w = estimate_min_width_px(disp, header_name, column_metadata, has_histogram)
        base_config['ag_grid_specs'] = {'minWidth': min_w}
        # ag_grid_specs from column_metadata (e.g. init_sd carrying
        # {'wrapText': True, 'width': 400}) overlay on top of styling's
        # computed minWidth. Shallow merge — caller wins per-key.
        if 'ag_grid_specs' in column_metadata:
            base_config['ag_grid_specs'].update(column_metadata['ag_grid_specs'])

        # init_sd's delete_keys drops top-level keys that style_column added
        # by default — e.g. the tooltip_config that string / time / binary /
        # categorical / fallback branches unconditionally attach.
        for k in column_metadata.get('delete_keys', ()):
            base_config.pop(k, None)

        return base_config


class DefaultSummaryStatsStyling(DefaultMainStyling):
    requires_summary = [
        "_type",
        "dtype", "non_null_count", "null_count", "unique_count", "distinct_count",
        "mean", "std", "min",
        "median",
        "max",
        "most_freq", "2nd_freq", "3rd_freq", "4th_freq", "5th_freq"]
    pinned_rows = [
        obj_('dtype'),
        inherit_('non_null_count'),
        inherit_('null_count'),
        inherit_('unique_count'),
        inherit_('distinct_count'),
        inherit_('mean'),
        inherit_('std'),
        inherit_('min'),
        inherit_('median'),
        inherit_('max'),
        inherit_('most_freq'),
        inherit_('2nd_freq'),
        inherit_('3rd_freq'),
        inherit_('4th_freq'),
        inherit_('5th_freq')]

    df_display_name = "summary"
    data_key = "empty"
    summary_stats_key= 'all_stats'

class CleaningDetailStyling(DefaultMainStyling):
    df_display_name = "cleaning_detail"
    pinned_rows = [obj_("dtype"), pinned_histogram(), float_("str_bool_frac"), float_("regular_int_parse_frac"),
        float_("strip_int_parse_frac"), float_("us_dates_frac"), obj_("cleaning_name"), obj_("null_count")]
