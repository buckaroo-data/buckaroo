.. _Contributing:

====================
Contributing to DCEF
====================

DCEF is actively looking for contributors.  All forms of participation are welcome, from bug reports, to suggestions, to code contributions.


Developing in the Jupyter Lab environment
=========================================

The easiest way to develop and contribute to DCEF is to add ``Commands``.  When I use DCEF to clean and explore a new dataset, I firt try to use the built in DCEF commands in the UI.  When I want to perform a manipulation that doesn't yet exist in DCEF, I first drop down to raw pandas/python like I would before DCEF... Then I figure out how to expose that functionality as a ``Command``.  While working with manatee data, I recognized that a column was probably date times, but a ``to_datetime``  ``Command`` didn't exist.  So I wrote one.

.. code-block:: python

    pd.to_datetime(df['REPDATE']).head()
    #outputs ->
    #0   1974-04-03 00:00:00+00:00
    #1   1974-06-27 00:00:00+00:00
    #Name: REPDATE, dtype: datetime64[ns, UTC]

    #pd.to_datetime is the transform I want... so I write it as a Command
    #and add it to the w widget with the @w.add_command decorator
    @w.add_command
    class to_datetime(Command):
        command_default = [s('to_datetime'), s('df'), "col"]
        command_pattern = [None]
    
        @staticmethod 
        def transform(df, col):
            df[col] = pd.to_datetime(df[col])
            return df
    
        @staticmethod 
        def transform_to_py(df, col):
            return "    df['%s'] = pd.to_datetime(df['%s'])" % (col, col)


When you use the ``add_command`` decorator, the command is instantly added to the UI of the corresponding widget.  Subsequent re-evalutations of the same cell, will replace a ``Command`` in the widget with the same name.  This allows you to iteratively develop commands.

Once you have developed a ``Command`` you can either continue to use it internally as with the ``add_command`` decorator or you can open a PR and add it to the builtin commands for DCEF `all_transforms.py <https://github.com/paddymul/dcef/blob/main/dcef/all_transforms.py>`_.

The upside of just using the @add_command decorator is that you don't have to setup a development environment.

Setting up a development environment
====================================

First, you need to fork the project. Then setup your environment:

.. code-block:: bash

   # create a new conda environment
   conda create -n dcef-dev jupyterlab pandas nodejs yarn pip
   conda activate dcef-dev
   pip install build twine

   # download dcef from your GitHub fork
   git clone https://github.com/<your-github-username>/dcef.git
   # or start by cloning the main repo
   git clone https://github.com/paddymul/dcef.git

   # install JS dependencies and build js assets
   cd dcef
   yarn install

   # install DCEF in editable mode
   python -m pip install -ve .

   #in another shell, setup the typescript watcher
   conda activate dcef-dev
   yarn build && yarn watch
   #this will build the jupyter lab extension, and recompile on any code changes

   #start your jupyter lab server in another shell
   conda activate dcef-dev
   jupyter lab

   #work on your jupyter notebook from that lab server

.. note::
   Getting typescript updates from the widget into a jupyter lab notebook is a little tricky.  The following steps ensure that typescript code changes are picked up.



Loading typescript changes
==========================

I make my changes, confirm that ``yarn watch`` has successfully compiled them. **then** I follow these steps to ensure the new code is loaded

#. Go to the jupyter lab notebook in a browser
#. Click the Kernel Menu > Restart Kernel and Clear all outputs
#. Save the notebook
#. Reload the web browser
#. Execute the relevant cells

It is sometimes helpful to put a console.log in ``js/plugin.ts`` and check that the updated log statement shows up in the browser to make sure you are executing the code you think you are.


