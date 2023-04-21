.. _Contributing:

====================
Contributing to DCEF
====================

DCEF is actively looking for contributors.  All forms of participation are welcome, from bug reports, to suggestions, to code contributions.

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


