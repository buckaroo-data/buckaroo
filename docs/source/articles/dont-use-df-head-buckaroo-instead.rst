.. Buckaroo documentation master file, created by
   sphinx-quickstart on Wed Apr 19 14:07:15 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Don't use df.head(), try buckaroo instead
=========================================

* **Why using df.head() is an anti-pattern**

In tutorials and common use, whenever we inspect a new dataset with pandas and jupyter, the first command is inevitably ``df.head()``.  The next commands and cells dig into the contents of the dataframe.  In a *more perfect world* we would just be typing ``df`` and seeing a rendered dataframe.  Pandas has sensible defaults for its builtin table html rendering system that limits the number of rows and columns displayed in the interest of performance and visual compactness. Soon you find yourself playing with ``pd.options.display.(width|max_rows)`` and looking up sorting and filtering commands.  Some might remember these commands off the top of their head, but even so, typing them repeatedly is slow and litters the notebook with temp work.  Next you'll look up ``df.info()`` and ``df.describe()``



.. image:: https://raw.githubusercontent.com/paddymul/buckaroo-assets/main/quick-buckaroo.gif
   :alt: df.head() vs buckaroo annotated walkthrough
   :align: right



* **Buckaroo fixes this intuitively**


With the new release of buckaroo, we can stop using ``df.head()``. I have worked to make Buckaroo usable as the default table visualization for pandas dataframes. It does this through sensible defaults and down sampling. All columns are shown, if there are less than 10,000 rows, all rows are shown. If there are more than 10,000 rows, sampling is turned on. But not just any sampling, sampling that also includes the 5 largest and smallest values of each column. At this point you will have around 10k rows in the interactive widget, which can be sorted by any column. Summary stats are a toggle away.

Buckaroo is already the fastest table widget (comparison coming from my testing) for the jupyter notebook. Being fast isn't just a bragging rights matter. To be usable as the default dataframe display method, some performance guarantees are necessary. Having your kernel lock up for 30 seconds or longer is unacceptable. So the system has to make some decisions for you. this is why sampling is automatically turned on for larger datasets.

* **Common manipulations are also quickly available**

Finally the Buckaroo command UI is available with a single click. The command interface allows you to iterate through normal data cleaning operations with a GUI… while generating python code to perform the operations in a function. Want to drop a column, click the column then the "dropcol" button. 

* **What this means for your workflows**

When I worked with a trading desk at a hedge fund, every time I would show analysts a model the first thing they wanted to do was look at the raw and intermediate data. I would say "well obviously because of this command, the column will have these values”, the response would come "SHOW ME THE DATA". Many times the analyst was right. This key part of any analysis workflow is made unnecessarily difficult, partly because of tooling, partly because of calluses built up from the pain of tooling that doesn't support the workflow.

When working with data we are constantly doing exploratory data analysis, when you transform a dataframe with code, you should explore the resulting dataframe. Our tools should help that process, buckaroo does.  You can just visualize data frames and all of their important attributes with a single command.  This encourages you to look at the data instead of making assumptions about it.  This also leads to less cluttered notebooks.

* **Planned developments for the default table experience**

The biggest feature in this area is making the summary stats and column reordering algorithms pluggable.  This will speed up my own development of features. I also want to to experiment with running the initial analysis in a separate thread, dynamically sizing the sample size, this way I can ensure that the table always loads in a reasonable and tunable timeframe.  I will also be adding unit tests and integrating it with the pluggable stats algorithms (run a series of tests over user supplied summary stats to check for exceptions).  There are also performance improvements, histograms, automatic column grouping, column reordering, and group colors coming.

* **Try Buckaroo**

Install buckaroo with ``pip install buckaroo`` then import it into your notebook with ``import buckaroo``.  Buckaroo becomes the default dataframe viewer.  Give it a try and reach out about what you think.
