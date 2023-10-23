.. _using:

=============
Auto Cleaning
=============

By default buckaroo aggresively tries to type data and clean it up.

Better typing
-------------
What do I mean by cleaning types?  By default if an integer column contains a single missing value, pandas will use the ``float64`` dtype to represent that value as a NaN.  The autotyping functionality instead casts that as ``Int64`` a new type in pandas that allows ``NA`` values in Int columns.  Work is also done to constrain types to their narrowest, so if an int value is between 0 and 255, autotyping will cast that to `UInt8` using a single byte instead of 8 for a float64 or int64.


Heuristic cleaning
------------------
The autocleaning tool also heursitically removes errant mistyped values from column.  If a column is primarily Ints with a single string, that string is stripped so the column can be treated as numeric.



Using Autocleaning
==================

Changing individual coercions
----------------------------

Autotyping operations are added to the lowcode UI by default, open up the lowcode UI with the λ menu, then click on operations and delete them with the X.


Turning off auto cleaning
-------------------------

Buckaroo's auto cleaning is aggressive and sometimes not wanted to use Buckaroo without autotyping, invoke it this way
.. code-block:: python

from buckaroo import BuckarooWidget
BuckarooWidget(df, autoType=False)





How Autotyping Works
====================

There are three steps to auto_cleaning

First frequency metadata is collected with ``get_typing_metadata``, this is a dictionary with ``0`` - ``1`` ranges for the proportion of values that could be ``int``, ``float``, ``bool``, ``datetime``.

Next ``recommend_type`` takes the typing metadata and returns ``bool``, ``datetime``, ``int``, ``float``, or ``string``

Finally ``emit_command`` returns a JLisp operation that will perform the conversion.


Why three functions?
--------------------

Splitting this into three distinct phases makes it much easier to customize behavior.  It also allows improvements to accrue without requiring complete rewrites of the auto-typing functionality.  My guess is that ``recommend_type`` is the easiest to override, and will be the most frequently.


How do I add special replacement functionality?
-----------------------------------------------

What if you commonly deal with a dataset that treats ``y`` as ``True`` and ``n`` as ``False``, how would you recognize those types of values and convert them to boolean?

Code coming soon.


