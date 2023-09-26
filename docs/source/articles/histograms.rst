.. _using:

==========
Histograms
==========

Buckaroo uses histograms to convey the general shape of a colum in the minimum amount of screen real estate.  Like the rest of buckaroo, this is an opionated feature.


Simple histograms for numeric columns
=====================================

Histograms traditionally show the distribution of values in a column allowing different distributions to be identified (normal distribution, bimodal, random, skew).  This works well for accurate data without outliers.

There are a couple types of outliers that mess up normal histogrrams.

Traditional histograms make no provision for NaNs.  There are two ways we could deal with NaN's treating them as another bar, or as an independent bar.  We chose a separate bar because NaNs are a property of the entire dataset and the histogram is a function of the relevant values.  NaNs are displayed in a different color and pattern.

Sentinel values.  Columns frquently have sentinel values mixed in to convey missing data or some special condition.  After dropping NaNs, we then look at the value counts, here is one explanation of a sampling

imagine a dataset inserts 0 for NaNs, without 0's the range of numbers goes from 55 to 235, 0's account for 10% of observations.  0 is obviosuly a sentinel here and should be plotted as a categorical.  If you disagree you can write your own histogram implementation and plug it in with the pluggable analysis framework.

Extreme values.  Buckaroo limits the extents of the set where the histogram is computed so that of the 10 bins, no single bin represents more than 50% of samples, limited to the quantile range from (0.1 to 0.9).  The reasoning is that the extreme values represent errant values if they are so far off that they mess up the range of the rest of the histogram.  I haven't decided how to convey which quantile range was chosen.


Categorical Histograms for everything else
==========================================

Histograms are generally considered for numeric columns. Most datasets have many categorical or non numeric values, how can we get a quick overview of them?

Well we already know how to plot NaNs, there are three other sentinel values that matter False, True, and "0".

Remaining categoricals are plotted as a long tail plot, most frequent on the left with decreasing frequency to the right.  The top 7 most frequent values are plotted, with a final bar of "long tail" consisting of the sum of all the remaining values"


Objections to this approach
===========================

This is not a traditional histogram and should not be read as such.  It is the best way to show the most insight about frequency of values in a column that we could come up with.


Other research
==============

https://edwinth.github.io/blog/outlier-bin/

https://stackoverflow.com/questions/11882393/matplotlib-disregard-outliers-when-plotting
references

        Boris Iglewicz and David Hoaglin (1993), "Volume 16: How to Detect and
        Handle Outliers", The ASQC Basic References in Quality Control:
        Statistical Techniques, Edward F. Mykytka, Ph.D., Editor.



	
