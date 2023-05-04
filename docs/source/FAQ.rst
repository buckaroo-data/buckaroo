.. Buckaroo documentation master file, created by
   sphinx-quickstart on Wed Apr 19 14:07:15 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Buckaroo - FAQ
==========================================


* **Why did you use LISP?**

  This is a problem domain that required a DSL and intermediate language.  I could have written my own or chosen an existing language.  I chose LISP because it is simple to interpret and generate, additionally it is well understood.  Yes LISP is obscure, but it is less obscure than a custom language I would write myself.  I didn't want to expose an entire progrmaming language with all the attendant security risks, I wanted a small safe strict subset of programming features that I explicitly exposed.  LISP is easier to manipulate as an AST than any language in PL history.  I am not yet using any symbolic manipulation facilities of LISP, and will probably only use them in limited ways. 

* **Do I need to know LISP to use DCF?**

  No.  Users of DCF will never need to know that LISP is at the core of the system.

* **Do I need to know LISP to contribute to DCF?**

  Not really.  Commands are added to the dcf interpreter via the Command class.  Commands are very simple and straight forward.  Here are the two functions that make `fillna` work.

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

*  **Is DCF meant to repalce knowledge of python/pandas**

   No, DCF helps experienced pandas devs quickly build and try the transformations they already know.  Transformation names stay very close to the underlying pandas names.  DCF makes different transforms more discoverable than reading obscure blogposts and half working stackoverflow submissions.  Different transformations can be quickly tried without a lot of reading and tinkering to see if it is the transform you want.  Finally, all transformations are emitted as python code.  That python code can be a starting point.



