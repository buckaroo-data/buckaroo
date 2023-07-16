.. Buckaroo documentation master file, created by
   sphinx-quickstart on Wed Apr 19 14:07:15 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Buckaroo - FAQ
==========================================

* **Does Buckaroo work in Visual Studio Code**

  As of 0.3.6 Buckaroo works properly in Visual Studio Code.  You must install the `Visual Studio Code Jupyter Extension <https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter>`_ and the `Jupyter Renderer extension <https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter-renderers>`_.  Then install buckaroo from pip and everything should work.

* **Does Buckaroo work with Google Colab**

Yes Buckaroo has been tested to work with Google Colab.

* **Does Buckaroo work with Jupyter Notebook**

Right now, buckaroo only works with the latest release - NB7.  The recommended way to run buckaroo is with "jupyter lab".  It could be possible to make buckaroo work with the older notebook versions, but this takes significant packaging work.  File a bug, when support for previous versions of Notebook becomes a serious barier to buckaroo adoption, it will be addressed.

*  **Are there any similar projects to Buckaroo?**

There are a couple of projects like Buckaroo that aim to provide a better table widget and pandas editing experience.

#. `Mito <https://github.com/mito-ds/monorepo>`_.  Source Available table/code editing widget for Jupyter.  More aimed at easing transition to pandas from excel users.  GNU Affero licensed
#. `Microsoft DataWrangler <https://github.com/microsoft/vscode-data-wrangler>`_ .  Closed source, provides a very similar experience inside of VSCode's notebook experience.  Only works inside of VSCode by the `VS Marketplace Terms of Use <https://cdn.vsassets.io/v/M190_20210811.1/_content/Microsoft-Visual-Studio-Marketplace-Terms-of-Use.pdf>`_
#. `IpyDatagrid <https://github.com/bloomberg/ipydatagrid>`_.  Open source.  Bloomberg's Jupyter table widget. I used the ipydatagrid repo structure as the basis for buckaroo (js build setup only)
#. `IPyAgGrid <https://github.com/widgetti/ipyaggrid>`_ .  Open source.  Wraps `AG Grid <https://www.ag-grid.com/>`_  in a jupyter widget.  Buckaroo also uses AG Grid.
#. `Bamboolib <https://github.com/tkrabel/bamboolib>`_  An originally open source tool aimed at building a similar experience, more aimed as a low-code tool for beginners.  The parent company 8080labs was acquired by Databricks.  Code no longer available.
#. `QGrid <https://github.com/quantopian/qgrid>`_.  Open source, unmaintained.  A slick table widget built by Quantopian, no code gen or data manipulation features


To be clear, I had the idea for building Buckaroo like this before I saw any of the other projects... But they are all open source and we can learn from each other.  If Buckaroo doesn't quite do what you want, check out one of the others

*  **Is Buckaroo meant to repalce knowledge of python/pandas**

   No, Buckaroo helps experienced pandas devs quickly build and try the transformations they already know.  Transformation names stay very close to the underlying pandas names.  Buckaroo makes different transforms more discoverable than reading obscure blogposts and half working stackoverflow submissions.  Different transformations can be quickly tried without a lot of reading and tinkering to see if it is the transform you want.  Finally, all transformations are emitted as python code.  That python code can be a starting point.


* **How well does Buckaroo perform on large dataframes**

  If Buckaroo is configured to send the entire dataframe to the frontend table widget, performance can be slow. But because Buckaroo is built to seamlessly present summary statistics and use sampling. You can operate on just a representative subset of the data, this is much more performant.  Manually scanning through more than 500 rows makes it way to easy to miss data anomalies.  Furthermore, Buckaroo separates the intent of a transform from the implementation.  Python code gen that does the same transform can be improved.  It also makes it quick to generate more complex code that is faster than a shorter implementation.  If you are coding yourself, you're more likely to write the short version vs painstakingly reproducing a fast implementation.


* **Why did you use LISP?**

  This is a problem domain that required a DSL and intermediate language.  I could have written my own or chosen an existing language.  I chose LISP because it is simple to interpret and generate, additionally it is well understood.  Yes LISP is obscure, but it is less obscure than a custom language I would write myself.  I didn't want to expose an entire progrmaming language with all the attendant security risks, I wanted a small safe strict subset of programming features that I explicitly exposed.  LISP is easier to manipulate as an AST than any language in PL history.  I am not yet using any symbolic manipulation facilities of LISP, and will probably only use them in limited ways. 

* **Do I need to know LISP to use Buckaroo?**

  No.  Users of Bucakroo will never need to know that LISP is at the core of the system.

* **Do I need to know LISP to contribute to Buckaroo?**

  Not really.  Commands are added to the buckaroo interpreter via the Command class.  Commands are very simple and straight forward.  Here are the two functions that make `fillna` work.

.. code-block:: python
		
    def fillna(df, col, val):
        df.fillna({col:val}, inplace=True)
        return df

    def fillna_py(df, col, val):
        return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)


If you want to work on code transformations, then a knowledge of lisp and particularly lisp macros are helpful.

* **What is an example of a code transformation?**

  Imagine you have a `dropcol` command which takes a single column to drop, also imagine that there is a function `dropcols` which takes a list of columns to drop.

  It is easier to build the UI to emit individual `dropcol` commands, you will end up with more readable code when you have a single command that drops all columns.

  You could write a transform which reads all `dropcol` forms and rewrites it to a single `dropcols` command.

  Alternatively, you could write a command that instead of subtractively reducing a dataframe, builds up a new dataframe from an explicit list of columns.  That is also a type of transform that could be written.

