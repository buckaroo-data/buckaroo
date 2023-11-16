.. _using:

=======
Roadmap
=======

Buckaroo is maturing and I decided to write a roadmap


Priorities
==========

Buckaroo is still for the most part, pre-users.  It is maturing though, and feedback gathered can map some reasonable principles

* Function as a reliable replacement for the default display of dataframes

  * Exceptions in the basic display of a dataframe are a P1 error.
  * Dataframes that don't display are a P1 error.
  * Taking more than a second to display a dataframe with less than 1M values is a P2 error

* Buckaroo should do the least surprising thing.

  * autocleaning should be turned off by default.

* Bug/feature request priorities

  * This is the roadmap and I'll stick with it.
  * If a user has a feature/bug request, and that is preventing them from using Buckaroo, that gets priority.


Release Plans
=============


0.4 Series
----------


#. Documentation

   * Readme refresh
   * How to create a formatter
   * Pluggable analysis framework refresh
   * Customizing autocleaning
   * Customizing enable/instantiation
   * Order of operations Dataflow doc
#. Promotion
#. Devops improvements (CI, testing, end to end testing, packaging)

   * CI passing - Done
   * CI testing - Done
   * End to End testing - Done
   * CI version Bump - needed
   * Ruff python linter - needed
#. Jupyter notebook compatability

   * Google colab - Done
   * VSCode - Done
   * Warning message on notebook < 7 - Done
   * Notebook 6.0 compatability ???
#. Code cleanup

   * Typescript passes linter - Done
   * snake_case camelCase normalization
   * better naming
   * sub module organization
#. Python Repr bugs

   * List
   * Tuple
   * Nested list and tuple across python types (int, float, boolean)
   * Dictionary?
#. Formatters

   * DateTime formatter
   * Float formatter with specificity
#. Frontend

   * Autoclean toggle


0.5 series
----------
I'm a bit fuzzy on this one, it's either going to be a backend port to polars or filtering.  I'll write it as filtering for now

#. Filtering

   * any field text search
   * Should work with codegen
   * Per column exact filtering
#. Additional sampling techniques

   * Chunks (50 contiguous rows)
   * Outliers - extent percentile for each colum all in a single view
   * Straight random sample
#. UI cycling

   * Everything that is now binary (summary stats on or off), is actually a single choice of multiple possible choices.  Allow multiple clicks to cycle through different options.
   * Enable cycling for summary_stats and sample method
#. Low code UI

   * Add Commands for filtering

0.6 series
----------
Polars backend

All of the same tests should pass.

#. Lowcode UI Commands in polars

   * Gives auto cleaning and filtering at much higher performance. Nice way to dip my feet into polars.
   * Testing that verifies ``eval(_to_py) == transform(df)`` and ``pl.transform(df) == pd.transform(df)``
   * pandas and polars equivalence is key to code gen continuing to be useful
#. Serialization in polars

   * 2x speed bump
   * straight forward
#. Pluggable analysis framework - for polars

   * Same pluggable analysis framework, now lazy
   * Summary stats run on whole dataframe - up to 1Gig

0.7 series
----------

#. serialization speedup

   * integrate parquest_wasm in the frontend
   * parquet serialization on the backend
   * maintain json serialization

