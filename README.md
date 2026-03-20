# Buckaroo - The Data Table for Jupyter

[![PyPI version](https://img.shields.io/pypi/v/buckaroo.svg)](https://pypi.org/project/buckaroo/)
[![CI](https://github.com/buckaroo-data/buckaroo/actions/workflows/checks.yml/badge.svg)](https://github.com/buckaroo-data/buckaroo/actions/workflows/checks.yml)
[![License](https://img.shields.io/pypi/l/buckaroo.svg)](https://github.com/buckaroo-data/buckaroo/blob/main/LICENSE.txt)

Buckaroo is a modern data table for Jupyter that expedites the most common exploratory data analysis tasks. The most basic data analysis task - looking at the raw data, is cumbersome with the existing pandas tooling. Buckaroo starts with a modern performant data table that is sortable, has value formatting, and scrolls infinitely. On top of the core table experience, extra features like summary stats, histograms, smart sampling, auto-cleaning, and a low code UI are added. All of the functionality has sensible defaults that can be overridden to customize the experience for your workflow.

<img width="947" alt="Screenshot 2025-05-12 at 3 54 33 PM" src="https://github.com/user-attachments/assets/9238c893-8dd4-47e4-8215-b5450c8c7b3a" />

## Try it now with Marimo in your browser
Play with Buckaroo without any installation.
[Full Tour](https://marimo.io/p/@paddy-mullen/buckaroo-full-tour)


## Quick start

```bash
pip install buckaroo
```

Then in a Jupyter notebook:

```python
import pandas as pd
import buckaroo
pd.DataFrame({'a': [1, 2, 10, 30, 50, 60, 50], 'b': ['foo', 'foo', 'bar', pd.NA, pd.NA, pd.NA, pd.NA]})
```

When you `import buckaroo`, it becomes the default display for Pandas and Polars DataFrames.

## Claude Code MCP Integration

Buckaroo can be used as an [MCP](https://modelcontextprotocol.io/) server in [Claude Code](https://docs.anthropic.com/en/docs/claude-code), giving Claude the ability to open data files in an interactive table viewer.

### Install

```bash
claude mcp add buckaroo-table -- uvx --from "buckaroo[mcp]" buckaroo-table
```

That's it. This downloads Buckaroo from PyPI into an isolated environment and registers the MCP server. No other installation steps are needed.

### Usage

Once installed, ask Claude Code to view any CSV, TSV, Parquet, or JSON file:

> show me sales_data.csv

Claude will call the `view_data` tool, which opens the file in Buckaroo's interactive table UI in your browser.


## Compatibility

Buckaroo works in the following notebook environments:

- `jupyter lab` (version >=3.6.0)
- `jupyter notebook` (version >=7.0)
- [Marimo](https://marimo.io/p/@paddy-mullen/buckaroo-full-tour)
- `VS Code notebooks` (with extra install)
- [Jupyter Lite](https://paddymul.github.io/buckaroo-examples/lab/index.html)
- `Google Colab`
- `Claude Code` (via MCP)

Buckaroo works with the following DataFrame libraries:
- **pandas** (version >=1.3.5)
- **polars** (optional, `pip install buckaroo[polars]`)


# Features

## High performance table
The core data grid is based on [AG-Grid](https://www.ag-grid.com/). It loads thousands of cells in under a second, with highly customizable display, formatting and scrolling. Data is loaded lazily into the browser as you scroll, and serialized with parquet. You no longer have to use `df.head()` to poke at portions of your data.

## Fixed width formatting by default
By default numeric columns are formatted to use a fixed width font and commas are added. This allows quick visual confirmation of magnitudes in a column.

## Histograms
[Histograms](https://buckaroo-data.readthedocs.io/en/latest/articles/histograms.html) for every column give you a very quick overview of the distribution of values, including uniques and N/A.

## Summary stats
The summary stats view can be toggled by clicking on the `0` below the `Σ` icon. Summary stats are similar to `df.describe` and extensible.

## Sorting
All visible data is sortable by clicking on a column name; further clicks change sort direction then disable sort for that column. Because extreme values are included with sample rows, you can see outlier values too.

## Search
Search is built into Buckaroo so you can quickly find the rows you are looking for.

## Lowcode UI
Buckaroo has a simple low code UI with Python code gen. This view can be toggled by clicking the checkbox below the `λ` (lambda) icon.

## Autocleaning
Select a cleaning method from the status bar. The autocleaning system inspects each column and runs statistics to decide if cleaning should be applied (parsing dates, stripping non-integer characters, parsing implied booleans like "yes"/"no"), then adds those operations to the low code UI. Different cleaning methods can be tried because dirty data isn't deterministic. Access it with `BuckarooWidget(df, auto_clean=True)`.

Read more: [Autocleaning docs](https://buckaroo-data.readthedocs.io/en/latest/articles/auto_clean.html)

## Extensibility at the core
Summary stats are built on the [Pluggable Analysis Framework](https://buckaroo-data.readthedocs.io/en/latest/articles/pluggable.html) that allows individual summary stats to be overridden, and new summary stats to be built in terms of existing ones. Care is taken to prevent errors in summary stats from preventing display of a dataframe.


# Learn More

## Interactive Styling Gallery
The interactive [styling gallery](https://py.cafe/app/paddymul/buckaroo-gallery) lets you see different styling configurations. You can live edit code and play with different configs.

## Videos
- [Buckaroo Full Tour](https://youtu.be/t-wk24F1G3s) 6m50s - A broad introduction to Buckaroo
- [The Column's the limit - PyData Boston 2025](https://www.youtube.com/watch?v=JUCvHnpmx-Y) 43m - How LazyBuckaroo reliably processes laptop-large data
- [19 Million row scrolling and stats demo](https://www.youtube.com/shorts/x1UnW4Y_tOk) 58s
- [Buckaroo PyData Boston 2025](https://www.youtube.com/watch?v=HtahDDEnBwE) 49m - Full tour with audience Q&A
- [Using Buckaroo and pandas to investigate large CSVs](https://www.youtube.com/watch?v=_ZmYy8uvZN8) 9m
- [Autocleaning quick demo](https://youtube.com/shorts/4Jz-Wgf3YDc) 2m38s
- [Writing your own autocleaning functions](https://youtu.be/A-GKVsqTLMI) 10m10s
- [Extending Buckaroo](https://www.youtube.com/watch?v=GPl6_9n31NE) 12m56s
- [Styling Buckaroo](https://www.youtube.com/watch?v=cbwJyo_PzKY) 8m18s
- [Understanding JLisp in Buckaroo](https://youtu.be/3Tf3lnuZcj8) 12m42s
- [GeoPandas Support](https://youtu.be/8WBhoNjDJsA)

## Articles
- [Using Buckaroo and pandas to investigate large CSVs](https://medium.com/@paddy_mullen/using-buckaroo-and-pandas-to-investigate-large-csvs-2a200aebae31)
- [Speed up exploratory data analysis with Buckaroo](https://medium.com/data-science-collective/speed-up-initial-data-analysis-with-buckaroo-71d00660d3fc)


## Example Notebooks

- [Full Tour (Marimo)](https://marimo.io/p/@paddy-mullen/buckaroo-full-tour) - Start here. Broad overview of Buckaroo's features. Also available on [Google Colab](https://colab.research.google.com/github/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Full-tour-colab.ipynb) and [JupyterLite](https://paddymul.github.io/buckaroo-examples/lab/index.html?path=Full-tour.ipynb)
- [Notebook on GitHub](https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Full-tour.ipynb)
- [Live Styling Gallery](https://marimo.io/p/@paddy-mullen/buckaroo-styling-gallery) - Examples of all the formatters and styling available
- [Live Autocleaning](https://marimo.io/p/@paddy-mullen/buckaroo-auto-cleaning) - How autocleaning works and how to implement your own
- [Live Histogram Demo](https://marimo.io/p/@paddy-mullen/buckaroo-histogram-demo) - Explanation of the embedded histograms
- [Live JLisp overview](https://marimo.io/p/@paddy-mullen/jlisp-in-buckaroo) - The small lisp interpreter powering the lowcode UI
- [Extending Buckaroo](https://paddymul.github.io/buckaroo-examples/lab/index.html?path=Extending.ipynb) - Adding post processing methods and custom styling
- [Styling Howto](https://paddymul.github.io/buckaroo-examples/lab/index.html?path=styling-howto.ipynb) - In depth custom styling guide
- [Pluggable Analysis Framework](https://paddymul.github.io/buckaroo-examples/lab/index.html?path=Pluggable-Analysis-Framework.ipynb) - Adding new summary stats
- [Solara Buckaroo](https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/Solara-Buckaroo.ipynb) - Using Buckaroo with Solara
- [GeoPandas with Buckaroo](https://github.com/buckaroo-data/buckaroo/blob/main/docs/example-notebooks/GeoPandas.ipynb)

## Example apps built on Buckaroo
- [Buckaroo Compare](https://marimo.io/p/@paddy-mullen/buckaroo-compare-preview) - Join two dataframes and highlight visual differences
- [Buckaroo Pandera](https://marimo.io/p/@paddy-mullen/buckaroo-pandera) - Validate a dataframe with Pandera, then visually highlight where it fails


# Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, build instructions, and release process.

We welcome [issue reports](https://github.com/buckaroo-data/buckaroo/issues); be sure to choose the proper issue template so we get the necessary information.
