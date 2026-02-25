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
