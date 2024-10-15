import json
import re
import pandas as pd
import numpy as np
import solara
from buckaroo.solara_buckaroo import SolaraDFViewer

float_col = [5, -8, 13.23, -8.01, -999.345245234, None]
float_df = pd.DataFrame({
    'float_obj_displayer': float_col,
    'float_float_displayer_1__3': float_col,
    'float_float_displayer_0__3': float_col,
    'float_float_displayer_3__3': float_col,
    'float_float_displayer_3_13': float_col})

def float_col_conf(min_digits, max_digits):
    return {'displayer_args': { 'displayer': 'float', 'min_fraction_digits':min_digits, 'max_fraction_digits': max_digits}}

float_config = {
        'float_obj_displayer':  {'displayer_args': {'displayer': 'obj'}},      
        'float_float_displayer_1__3' : float_col_conf(1,3),
        'float_float_displayer_0__3' : float_col_conf(0,3),
        'float_float_displayer_3__3' : float_col_conf(3,3),
        'float_float_displayer_3_13' : float_col_conf(3,13)}


base_str_col = ["asdf", "qwerty", "really long string, much  much longer",
             None,  "A"]

str_df = pd.DataFrame({
        'strings_string_displayer_max_len': base_str_col,
        'strings_obj_displayer':  base_str_col,
        'strings_string_displayer': base_str_col,
})
str_config =  {
        'strings_string_displayer_max_len': {'displayer_args': {'displayer': 'string', 'max_length':35}},
        'strings_obj_displayer':  {'displayer_args': {'displayer': 'obj'}},      
        'strings_string_displayer': {'displayer_args': {'displayer': 'string'}},
    }


ts_col = ["2020-01-01 01:00Z", "2020-01-01 02:00Z", "2020-02-28 02:00Z", "2020-03-15 02:00Z", None]
datetime_df = pd.DataFrame(
    {'timestamp':ts_col,
     'timestamp_obj_displayer':ts_col,
     'timestamp_datetime_default_displayer':ts_col,
     'timestamp_datetime_locale_en-US':ts_col,
     'timestamp_datetime_locale_en-US-Long':ts_col,
     'timestamp_datetime_locale_en-GB':ts_col})


def locale_col_conf(locale, args={}):
    return {'displayer_args': {'displayer': 'datetimeLocaleString',
                                'locale':locale,
                                'args':args}}
datetime_config = {
    'timestamp_obj_displayer':  {'displayer_args': {'displayer': 'obj'}},    
    'timestamp_datetime_default_displayer' : {'displayer_args':  {  'displayer': 'datetimeDefault'}},
    'timestamp_datetime_locale_en-US' :locale_col_conf('en-US'),
    'timestamp_datetime_locale_en-US-Long': locale_col_conf('en-US', { 'weekday': 'long'}),
    'timestamp_datetime_locale_en-GB' : locale_col_conf('en-GB')}

link_df = pd.DataFrame({'raw':      ['https://github.com/paddymul/buckaroo', 'https://github.com/pola-rs/polars'],
                    'linkify' : ['https://github.com/paddymul/buckaroo', 'https://github.com/pola-rs/polars']})
link_config = {'linkify': {'displayer_args':  {  'displayer': 'linkify'}}}

#fixme no underline or blue highlighting of links... but they are links


# I pulled this out into a separate variable so we can eventually
# display it in a spearate code block
histogram_data = ['histogram', 
          [{'name': 'NA', 'NA': 100.0}],
          [{'name': 1, 'cat_pop': 44.0}, {'name': 'NA', 'NA': 56.0}],
          [{'name': 'long_97', 'cat_pop': 0.0},
           {'name': 'long_139', 'cat_pop': 0.0},
           {'name': 'long_12', 'cat_pop': 0.0},
           {'name': 'long_134', 'cat_pop': 0.0},
           {'name': 'long_21', 'cat_pop': 0.0},
           {'name': 'long_44', 'cat_pop': 0.0},
           {'name': 'long_58', 'cat_pop': 0.0},
           {'name': 'longtail', 'longtail': 77.0},
           {'name': 'NA', 'NA': 20.0}],
          [{'name': 'long_113', 'cat_pop': 0.0},
           {'name': 'long_116', 'cat_pop': 0.0},
           {'name': 'long_33', 'cat_pop': 0.0},
           {'name': 'long_72', 'cat_pop': 0.0},
           {'name': 'long_122', 'cat_pop': 0.0},
           {'name': 'long_6', 'cat_pop': 0.0},
           {'name': 'long_83', 'cat_pop': 0.0},
           {'name': 'longtail', 'unique': 50.0, 'longtail': 47.0}]]
histogram_df = pd.DataFrame({
    'names': ['index', 'all_NA', 'half_NA', 'longtail', 'longtail_unique'],
    'histogram_props': histogram_data})

histogram_config={
    'histogram_props': {'displayer_args': {'displayer': 'histogram'}}}

png_smiley = 'iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAApgAAAKYB3X3/OAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAANCSURBVEiJtZZPbBtFFMZ/M7ubXdtdb1xSFyeilBapySVU8h8OoFaooFSqiihIVIpQBKci6KEg9Q6H9kovIHoCIVQJJCKE1ENFjnAgcaSGC6rEnxBwA04Tx43t2FnvDAfjkNibxgHxnWb2e/u992bee7tCa00YFsffekFY+nUzFtjW0LrvjRXrCDIAaPLlW0nHL0SsZtVoaF98mLrx3pdhOqLtYPHChahZcYYO7KvPFxvRl5XPp1sN3adWiD1ZAqD6XYK1b/dvE5IWryTt2udLFedwc1+9kLp+vbbpoDh+6TklxBeAi9TL0taeWpdmZzQDry0AcO+jQ12RyohqqoYoo8RDwJrU+qXkjWtfi8Xxt58BdQuwQs9qC/afLwCw8tnQbqYAPsgxE1S6F3EAIXux2oQFKm0ihMsOF71dHYx+f3NND68ghCu1YIoePPQN1pGRABkJ6Bus96CutRZMydTl+TvuiRW1m3n0eDl0vRPcEysqdXn+jsQPsrHMquGeXEaY4Yk4wxWcY5V/9scqOMOVUFthatyTy8QyqwZ+kDURKoMWxNKr2EeqVKcTNOajqKoBgOE28U4tdQl5p5bwCw7BWquaZSzAPlwjlithJtp3pTImSqQRrb2Z8PHGigD4RZuNX6JYj6wj7O4TFLbCO/Mn/m8R+h6rYSUb3ekokRY6f/YukArN979jcW+V/S8g0eT/N3VN3kTqWbQ428m9/8k0P/1aIhF36PccEl6EhOcAUCrXKZXXWS3XKd2vc/TRBG9O5ELC17MmWubD2nKhUKZa26Ba2+D3P+4/MNCFwg59oWVeYhkzgN/JDR8deKBoD7Y+ljEjGZ0sosXVTvbc6RHirr2reNy1OXd6pJsQ+gqjk8VWFYmHrwBzW/n+uMPFiRwHB2I7ih8ciHFxIkd/3Omk5tCDV1t+2nNu5sxxpDFNx+huNhVT3/zMDz8usXC3ddaHBj1GHj/As08fwTS7Kt1HBTmyN29vdwAw+/wbwLVOJ3uAD1wi/dUH7Qei66PfyuRj4Ik9is+hglfbkbfR3cnZm7chlUWLdwmprtCohX4HUtlOcQjLYCu+fzGJH2QRKvP3UNz8bWk1qMxjGTOMThZ3kvgLI5AzFfo379UAAAAASUVORK5CYII='

img_df = pd.DataFrame({'raw':            [png_smiley, None],
                    'img_displayer' : [png_smiley, None]})
img_config = {
    'raw':           {'displayer_args': {'displayer': 'string', 'max_length':40}},
    'img_displayer': {'displayer_args': {'displayer': 'Base64PNGImageDisplayer'},
                      'ag_grid_specs' : {'width':150}}}

ROWS = 200
#the next dataframe is used for multiple examples
typed_df = pd.DataFrame(
    {'int_col':np.random.randint(1,50, ROWS),
     'float_col': np.random.randint(1,30, ROWS)/.7,
     "str_col": ["foobar"]* ROWS})
tooltip_config = {
        'str_col':
            {'tooltip_config': { 'tooltip_type':'simple', 'val_column': 'int_col'}}}

colormap_config = {
        'float_col': {'color_map_config': {
          'color_rule': 'color_map',
          'map_name': 'BLUE_TO_YELLOW',
        }}}

error_df = pd.DataFrame({
    'a': [10, 20, 30],
    'err_messages': [None, "a must be less than 19, it is 20", "a must be less than 19, it is 30"]})

error_config = {
        'a': {'color_map_config': {
            'color_rule': 'color_not_null',
            'conditional_color': 'red',
            'exist_column': 'err_messages'}}}

color_df = pd.DataFrame({
    'a': [10, 20, 30],
    'a_colors': ['red', '#d3a', 'green']})

color_from_col_config={
        'a': { 'color_map_config': {
          'color_rule': 'color_from_column',
          'col_name': 'a_colors'}}}

configs = {"str_config" : (str_df, str_config),
           "float_config": (float_df, float_config),
           "datetime_config": (datetime_df, datetime_config),
           "link_config": (link_df, link_config),
           "histogram_config": (histogram_df, histogram_config),
           "img_config": (img_df, img_config),
           "tooltip_config": (typed_df, tooltip_config),
           "colormap_config": (typed_df, colormap_config),
           "error_config": (error_df, error_config),
           "color_from_col_config": (color_df, color_from_col_config),
           
           }

active_config = solara.reactive("float_config")

gallery_css = """
.dfviewer-widget {min-width:70vw}
span.span { background: red;}
.config-select {width:300px; }
"""


def format_json(obj):
    """
      Formats obj to json  string to remove unnecessary whitespace.
      Returns:
          The formatted JSON string.
    """
    json_string = json.dumps(obj, indent=4)
    # Remove whitespace before closing curly braces
    formatted_string = re.sub(r'\s+}', '}', json_string)

    return formatted_string

@solara.component
def Page():
    #solara.Style(Path("gallery.css"))
    solara.Style(gallery_css)
    solara.Markdown("""
# Buckaroo Styling Gallery

Select a config, and view the output.  Each dataframe has multiple columns with the exact same values. The display differs because of the column config applied.

    
    """)
    solara.Select(label="Config",
        value=active_config, 
        values=list(configs.keys()),
        dense=True,
        classes=["config-select"]
    )

    conf = configs[active_config.value]
    formatted_conf = format_json(conf[1]) #json.dumps(conf[1], indent=4)

    json_code = f"""
```python
{formatted_conf}
```"""

    with solara.HBox():


        with solara.Column(gap="10px"):
            solara.Text("Column Config")
            solara.Markdown(json_code, style="min-width:400px;")
        with solara.Column(gap="10px"):
            solara.Text("Buckaroo Widget")

            SolaraDFViewer(df=conf[0],
                column_config_overrides = conf[1],
                pinned_rows=[]
            )


