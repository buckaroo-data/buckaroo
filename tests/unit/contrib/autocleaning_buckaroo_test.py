import pandas as pd
from buckaroo.buckaroo_widget import AutocleaningBuckaroo

dirty_df = pd.DataFrame(
    {
        "a": [10, 20, 30, 40, 10, 20.3, None, 8, 9, 10, 11, 20, None],
        "b": [
            "3",
            "4",
            "a",
            "5",
            "5",
            "b9",
            None,
            " 9",
            "9-",
            11,
            "867-5309",
            "-9",
            None,
        ],
        "us_dates": [
            "",
            "07/10/1982",
            "07/15/1982",
            "7/10/1982",
            "17/10/1982",
            "03/04/1982",
            "03/02/2002",
            "12/09/1968",
            "03/04/1982",
            "",
            "06/22/2024",
            "07/4/1776",
            "07/20/1969",
        ],
        "mostly_bool": [
            True,
            "True",
            "Yes",
            "On",
            "false",
            False,
            "1",
            "Off",
            "0",
            " 0",
            "No",
            1,
            None,
        ],
    }
)

expected_df = pd.DataFrame(
    {
        "a": [10, 20, 30, 40, 10, 20.3, None, 8, 9, 10, 11, 20, None],
        "b": pd.Series([
            3,
            4,
            None,
            5,
            5,
            9,
            None,
            9,
            9,
            11,
            8675309,
            -9,
            None,
        ], dtype='Int32'),
        "us_dates": [
            "",
            "07/10/1982",
            "07/15/1982",
            "7/10/1982",
            "17/10/1982",
            "03/04/1982",
            "03/02/2002",
            "12/09/1968",
            "03/04/1982",
            "",
            "06/22/2024",
            "07/4/1776",
            "07/20/1969",
        ],
        "mostly_bool": [
            True,
            "True",
            "Yes",
            "On",
            "false",
            False,
            "1",
            "Off",
            "0",
            " 0",
            "No",
            1,
            None,
        ],
    }
)


def test_aggressive_autocleaning():
    acb = AutocleaningBuckaroo(dirty_df)
    acb.buckaroo_state = {
    "cleaning_method": "aggressive",
    "post_processing": "",
    "sampled": False,
    "show_commands": False,
    "df_display": "main",
    "search_string": "",
    "quick_command_args": {}
    }
    
