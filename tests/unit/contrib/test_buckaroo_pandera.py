
import pandas as pd
import pandera.pandas as pa
from pandera import Column, Check
from buckaroo.contrib.buckaroo_pandera import BuckarooPandera


def test_buckaroo_pandera():
    fruits = pd.DataFrame({"name": ["apple", "banana", "apple", "orange"], "store": ["Aldi", "Walmart", "Walmart", "Aldi"], "price": [-3, 1, 2, 4]})
    available_fruits = ["apple", "banana", "orange"]
    nearby_stores = ["Aldi", "Walmart"]

    schema = pa.DataFrameSchema({"name": Column(str, Check.isin(available_fruits)), "store": Column(str, Check.isin(nearby_stores)), "price": Column(int, Check.greater_than(0))})
    BuckarooPandera(fruits, schema)
    assert 1==1
