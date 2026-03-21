
# Dastardly Dataframe Dataset

Static addition to docs,  pandas code blocks of weird dataframes, then the statically rendered bukaroo widget

talk about the dastardly dataframe dataset, and why these dataframes are generally hard to display,  what little things trip people up

Note that although the types are rare, because buckaroo is built not as a customized table widget for use in dashboards but a way to see dataframes as they are in data workflow systems, being able to display all types is pretty important.

Also note that this is a static embedding of the DFViewer, part of the new DFViewer embeddable system so you can integrate buckaroo into your apps simply.  more coming on the embeddable buckaroo

# DDD for polars

new release of the buckaroo static embedding that now supports polars.  once again talk about the DDD.  specifically https://github.com/buckaroo-data/buckaroo/issues/622

# Static embedding improvements

## publish the JS to a CDN -> reduced embed size talk about size reductions
talk about how I bult this to better share what buckaroo is doing.  At first you needed to download jupyter and buckaroo.  Then Marimo Pyodide, now static embedding, now smaller static embedding

does pageweight even matter, well to buckaroo it does, to dbt, apparently not, their home page is 501KB compressed 801KB raw,  the whole thing is 28Mb, DOM Content loaded in 1.41 seconds (This buckaroo page will be better of course,  the old version will probalby be better)

Snowflake 128kb/1.28mb/22.51mb/445ms

Databricks 127kb/797kb/313ms

## Customizing buckaroo via api for embeds
show some styling, link to styling docs

## Static search

Maybe,  take a crack at it

Link to the static embedding guide

## Styling buckaroo chrome
based on 
https://github.com/buckaroo-data/buckaroo/pull/583

# Buckaroo embedding guide

Why to embed buckaroo
Which config makes sense for you - along with data sizes reasoning
Customizing appearache
Cusomizing buckaroo

# embedding buckaroo for bigger data
Parquet range queries on s3/r2 buckets
sponsored by cloudflare?




# How types and data move from engine to browser

Column renaming (a,b,c..z,aa,ab), type coercion before parquet, fastparquet encoding, base64 transport, hyparquet decode in browser, displayer/formatter dispatch. Full pipeline trace for a single cell value.

See `docs/source/articles/types-to-display.rst`

## Help me work through a content plan.

what other features have I recently released that desereve blog posts?
Should I just start here?

Where do these fit into the docs site?



