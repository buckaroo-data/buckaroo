# Buckaroo - The Data Table for Jupyter

Buckaroo is a modern data table for Jupyter that expedites the most common exploratory data analysis tasks. The most basic data analysis task - looking at the raw data, is cumbersome with the existing pandas tooling.  Buckaroo starts with a modern performant data table that displays up to 10k rows, is sortable, has value formatting, and scrolls.  On top of the core table experience extra features like summary stats, histograms, smart sampling, auto-cleaning, and a low code UI are added.  All of the functionality has sensible defaults that can be overridden to customize the experience for your workflow.

<img width="1002" alt="Polars-Buckaroo" src="https://github.com/paddymul/buckaroo/assets/40453/f48b701b-dfc4-4470-8588-05b6a9f33eec">


## Try it today

* [Buckaroo full tour](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/Full-tour.ipynb)[![Open In Colab](https://camo.githubusercontent.com/52feade06f2fecbf006889a904d221e6a730c194/68747470733a2f2f636f6c61622e72657365617263682e676f6f676c652e636f6d2f6173736574732f636f6c61622d62616467652e737667)](https://colab.research.google.com/github/paddymul/buckaroo/blob/main/example-notebooks/Full-tour.ipynb) Notebook

## Quick start

run `pip install buckaroo`
in a notebook execute the following to see Buckaroo

```
import pandas as pd
import buckaroo
pd.DataFrame({'a':[1, 2, 10, 30, 50, 60, 50], 'b': ['foo', 'foo', 'bar', pd.NA, pd.NA, pd.NA, pd. NA]})

```

When you run `import buckaroo` in a Jupyter notebook, Buckaroo becomes the default display method for Pandas and Polars DataFrames


## Compatibility

Buckaroo works in the following notebook environments

- `jupyter lab` (version >=3.6.0)
- `jupyter notebook` (version >=7.0) 
- `VS Code notebooks` (with extra install)
- `Google colab`  (with special initiation code)

Buckaroo works with the following DataFrame libraries
- `pandas` (version >=1.3.5)
- `polars` optional
- `geopandas` optional


# Learn More

Buckaroo has extensive docs and tests, the best way to learn about the system is from feature example videos on youtube


## Videos 
- [Extending Buckaroo](https://www.youtube.com/watch?v=GPl6_9n31NE)
- [Styling Buckaroo](https://www.youtube.com/watch?v=cbwJyo_PzKY)
- [GeoPandas Support](https://youtu.be/8WBhoNjDJsA)

## Example Notebooks

The following notebooks must executed in an environemnt with Buckaroo installed.
- [Full Tour](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/Full-tour.ipynb) Start here. This gives a broad overview of Buckaroo's features.
- [Histogram Demo](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/Histograms-demo.ipynb) Explantion of the embedded histograms of Buckaroo.
- [Styling Gallery](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/styling-gallery.ipynb) Examples of all of the different formatters and styling available for the table
- [Extending Buckaroo](http://localhost:8888/lab/workspaces/auto-p/tree/Extending.ipynb) Broad overview of how to add post processing methods and custom styling methods to Buckaroo
- [Styling Howto](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/styling-howto.ipynb) In depth explanation of how to write custom styling methods
- [Pluggable Analysis Framework](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/Pluggable-Analysis-Framework.ipynb) How to add new summary stats to Buckaroo
- [Solara Buckaroo](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/Solara-Buckaroo.ipynb) Using Buckaroo with Solara
- [GeoPandas with Bucakroo](https://github.com/paddymul/buckaroo/blob/main/example-notebooks/GeoPandas.ipynb)

# Features

## High performance table
The core data grid of buckaroo is based on [AG-Grid](https://www.ag-grid.com/). This loads 1000s of cells in less than a second, with highly customizable display, formatting and scrolling.  You no longer have to use `df.head()` to poke at portions of your data.

## Fixed width formatting by default

By default numeric columns are formatted to use a fixed width font and commas are added.  This allows quick visual confirmation of magnitudes in a column.

## Histograms

[Histograms](https://buckaroo-data.readthedocs.io/en/latest/articles/histograms.html) for every column give you a very quick overview of the distribution of values, including uniques and N/A.

## Summary stats
The summary stats view can be toggled by clicking on the `0` below the `Σ` icon.  Summary stats are similar to `df.describe` and extensible.

## Inteligent sampling

Buckaroo will display entire DataFrames up to 10k rows.  Displaying more than that would run into performance problems that would make display too slow.  When a DataFrame has more than 10k rows, Buckaroo samples a random set of 10k rows, and also adds in the rwos with the 5 most extreme values for each column.

## Sorting

All of the data visible in the table (rows shown), is sortable by clicking on a column name, further clicks change sort direction then disable sort for that column.  Because extreme values are included with sample rows, you can see outlier values too.

## Extensibility at the core

Buckaroo summary stats are built on the [Pluggable Analysis Framework](https://buckaroo-data.readthedocs.io/en/latest/articles/pluggable.html) that allows individual summary stats to be overridden, and new summary stats to be built in terms of existing summary stats.  Care is taken to prevent errors in summary stats from preventing display of a dataframe.

## Lowcode UI (beta)

Buckaroo has a simple low code UI with python code gen. This view can be toggled by clicking on the `0` below the ` λ ` icon.

## Auto cleaning (beta)

Buckaroo can [automatically clean](https://buckaroo-data.readthedocs.io/en/latest/articles/auto_clean.html) dataframes to remove common data errors (a single string in a column of ints, recognizing date times...).  This feature is in beta.  You can access it by invoking buckaroo as `BuckarooWidget(df, auto_clean=True)`

## Development installation

For a development installation:

```bash
git clone https://github.com/paddymul/buckaroo.git
cd buckaroo
#we need to build against 3.6.5, jupyterlab 4.0 has different JS typing that conflicts
# the installable still works in JL4
pip install build twine pytest sphinx polars mypy jupyterlab==3.6.5 pandas-stubs
pip install -ve .
```

Enabling development install for Jupyter notebook:


Enabling development install for JupyterLab:

```bash
jupyter labextension develop . --overwrite
```

Note for developers: the `--symlink` argument on Linux or OS X allows one to modify the JavaScript code in-place. This feature is not available with Windows.
`
### Developing the JS side

There are a series of examples of the components in [examples/ex](./examples/ex).



Instructions
```bash
npm install
npm run dev
```


## Contributions

We :heart: contributions.

Have you had a good experience with this project? Why not share some love and contribute code, or just let us know about any issues you had with it?

We welcome issue reports [here](../../issues); be sure to choose the proper issue template for your issue, so that we can be sure you're providing the necessary information.

