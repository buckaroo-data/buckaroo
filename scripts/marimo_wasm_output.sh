#!/bin/bash
filename=$1
mode=$2
notebook_name="${filename%.*}"

full_notebook_path="docs/example-notebooks/marimo-wasm/${filename}"
full_output_path="docs/extra-html/example_notebooks/${notebook_name}"
uv run marimo export html-wasm $full_notebook_path   -o $full_output_path   --mode $mode -f

#TODO  By default if there is a public directory in the source directory wiht the notebook, marimo will include it in the built output.  I would like to add an option to include the public directory.  the citibike parquet file is 2.5 mb


# Even better would be a docstring or commented annotation in the python file to control which files end up in the built notebook... That way I cna just iterate over all files in marimo-wasm and they are made into documentation notebooks



