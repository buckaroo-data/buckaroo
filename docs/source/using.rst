.. _using:

===========
Using Buckaroo
===========

Buckaroo is meant to be used in a jupyterlab notebook to clean and explore pandas dataframes.

Before you begin, make sure that you follow the steps in :ref:`install`.

The following sections cover how to use Buckaroo.


In a Jupyter Lab notebook cell
==============================

.. code-block:: python

    from buckaroo.buckaroo_widget import BuckarooWidget
    BuckarooWidget(df=df)  #df being the dataframe you want to explore


And you will see the UI for Buckaroo.

Using Commands
==============

At the core Buckaroo commands operate on columns.  You must first click on a cell (not a header) in the top pane to select a column.

Next you must click on a command like ``dropcol``, ``fillna``, or ``groupby`` to create a new command

After creating a new command, you will see that command in the commands list, now you must edit the details of a command.  Select the command by clicking on the bottom cell.

At this point you can either delete the command by clicking the ``X`` button or change command parameters.

Writing your own commands
=========================


Builtin commands are found in `all_transforms.py <https://github.com/paddymul/buckaroo/blob/main/buckaroo/all_transforms.py>`_


.. code-block:: python

    class DropCol(Command):
        command_default = [s('dropcol'), s('df'), "col"]
        command_pattern = [None]
    
        @staticmethod 
        def transform(df, col):
            df.drop(col, axis=1, inplace=True)
            return df
    
        @staticmethod 
        def transform_to_py(df, col):
            return "    df.drop('%s', axis=1, inplace=True)" % col


``command_default`` is the base configuration of the command when first added, ``s('dropcol')`` is a special notation for the function name.  ``s('df')`` is a symbol notation for the dataframe argument (see LISP section of the `FAQ` for details).  ``"col"`` is a placeholder for the selected column.

since ``dropcol`` does not take any extra arguments, ``command_pattern`` is ``[None]``
