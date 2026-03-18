#!/usr/bin/env python3
"""Generate a static embed test HTML file in buckaroo/static/ for Playwright testing."""
import sys
import os

# Ensure the repo root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from buckaroo.artifact import to_html

# Create a DataFrame with enough variety to exercise rendering
df = pd.DataFrame({
    'name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve',
             'Frank', 'Grace', 'Hank', 'Ivy', 'Jack'],
    'age': [25, 30, 35, 28, 42, 55, 23, 38, 31, 47],
    'score': [88.5, 92.1, 75.3, 96.7, 81.0, 67.2, 94.8, 73.6, 85.9, 90.4],
    'active': [True, False, True, True, False, True, True, False, True, False],
})

html = to_html(df, title="Buckaroo Static Embed Test")
out_path = os.path.join(os.path.dirname(__file__), '..', 'buckaroo', 'static', 'static-test.html')
with open(out_path, 'w') as f:
    f.write(html)
print(f"Generated {out_path}")

# BigInt precision test: INT64 values above Number.MAX_SAFE_INTEGER (2^53-1)
bigint_df = pd.DataFrame({
    'big_id': [9007199254740993, 9007199254740994, 9007199254740995],
    'label': ['a', 'b', 'c'],
})
bigint_html = to_html(bigint_df, title="BigInt Precision Test")
bigint_path = os.path.join(os.path.dirname(__file__), '..', 'buckaroo', 'static', 'bigint-test.html')
with open(bigint_path, 'w') as f:
    f.write(bigint_html)
print(f"Generated {bigint_path}")
