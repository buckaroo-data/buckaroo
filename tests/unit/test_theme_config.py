import pandas as pd
from buckaroo.buckaroo_widget import BuckarooWidget


simple_df = pd.DataFrame({'int_col': [1, 2, 3], 'str_col': ['a', 'b', 'c']})


def test_theme_flows_through_widget():
    theme = {'colorScheme': 'dark', 'accentColor': '#ff6600'}
    w = BuckarooWidget(simple_df, component_config={'theme': theme})
    cc = w.df_display_args['main']['df_viewer_config'].get('component_config', {})
    assert cc['theme'] == theme


def test_theme_absent_by_default():
    w = BuckarooWidget(simple_df)
    cc = w.df_display_args['main']['df_viewer_config'].get('component_config', {})
    assert 'theme' not in cc or cc.get('theme') is None


def test_full_theme_config_roundtrips():
    theme = {
        'colorScheme': 'dark',
        'accentColor': '#e91e63',
        'accentHoverColor': '#c2185b',
        'backgroundColor': '#1a1a2e',
        'foregroundColor': '#e0e0e0',
        'oddRowBackgroundColor': '#16213e',
        'borderColor': '#0f3460',
    }
    w = BuckarooWidget(simple_df, component_config={'theme': theme})
    cc = w.df_display_args['main']['df_viewer_config'].get('component_config', {})
    assert cc['theme'] == theme


def test_theme_with_other_component_config():
    """Theme coexists with other component_config properties."""
    theme = {'accentColor': '#ff6600'}
    w = BuckarooWidget(simple_df, component_config={'theme': theme, 'className': 'my-class'})
    cc = w.df_display_args['main']['df_viewer_config'].get('component_config', {})
    assert cc['theme'] == theme
    assert cc['className'] == 'my-class'
