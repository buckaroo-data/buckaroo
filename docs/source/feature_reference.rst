.. _Feature_reference:

=================
Feature Reference
=================

Full App Diagram
================
.. image:: _static/Buckaroo-labled.png
  :width: 281
  :alt: Full widget


Status Bar Features
===================
The status bar is displayed above every table, it allows quick toggling of different UI modes

.. image:: _static/Statusbar.png
  :width: 200
  :alt: Status Bar


Summary Statistics
------------------
To View Summary Statistics click on the Σ cell .  When the value below is ``1``, the summary stats view will be show in the table.

Command Editting Mode
---------------------

To turn on Command Editting mode, click on the λ cell.  This will bring up the command UI and the transformed dataframe view

Sampled Data Mode
-----------------

When a dataframe has more than 10k rows, Bucakroo inteligently downsamples the dataframe to only 10k rows + extents for each column.  Sometimes you want to see the entire dataframe, toggling the Ξ cell enables this.  Turning off sampling for large datasets can cause the table to take a long time to render, so use with caution.

Sort by a column
----------------

To sort the dataframe by any column, click on the header for that column, sorting will cycle through ``ascending``, ``descending`` and ``off``


