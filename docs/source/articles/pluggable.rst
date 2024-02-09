.. _using:

============================
Pluggable analysis framework
============================

The pluggable analysis framework is built to allow the different bits of analysis done by buckaroo to be mixed and matched as configuration, without requiring editting the core of buckaroo.  Pieces of analysis can build on each other, and errors are flagged intelligently.


Analysis In Action
==================

The most obvious piece of analysis is adding a new measure/fact to summary stats.

A monolithic summary_stats would look like this

.. code-block:: python

    def summarize_string(ser):
        l = len(ser)
        val_counts = ser.value_counts()
        distinct_count= len(val_counts)
    
        return dict(
            dtype=ser.dtype,
            length=l,
            min='',
            distinct_count= distinct_count,
            distinct_percent = distinct_count/l)
    
    def summarize_df(df):
        summary_df = pd.DataFrame({col:summarize_string(df[col]) for col in df})
        return summary_df
    
    
If you wanted to enhance that simple summary_stat by adding nan_count and nan_percent, you would have to rewrite the entire function and get buckaroo to use your new function.  Instead, imagine that the existing ``sumarize_string`` was already built into Buckaroo and you wanted to add to it. Here's what the code looks like.
    
    
.. code-block:: python

    bw = BuckarooWidget(df)
    @bw.add_analysis
    class NanStats(ColAnalysis):
        provided_summary = [
            'nan_count', 'nan_percent']
        requires_summary = ['length']
    
        @staticmethod
        def summary(sampled_ser, summary_ser, ser):
            l = summary_ser.loc['min']
            nan_count = l - len(ser.dropna())
            return dict(
    	    nan_count = nan_count,
                nan_percent = nan_count/l)
    bw  #render the buckaroo widget
    



Now buckaroo will be displayed with the new summary stats of 'nan_count' and 'nan_percent'.  Buckaroo knows that ``NanStats`` must be called after the ``ColAnalysis`` object that provides ``length`` and that ordering is handled for you automatically (via a DAG).

You can then iteratively and interactively update your analysis in the jupyter notebook focussing on the core of your business logic without worrying about how to structure your code.  When ``add_analysis`` is called, a set of simple unit tests are run that catch common errors with weird datashapes.  This means you can focus on coding and not worry about all the edge cases.


Features of the Pluggable Analysis Framework
============================================

Every aspect of the interactive experience of buckaroo can be manipulated through Analysis objects

summary_stats
    different facts can be added to the summary stats view... This is the most basic type of analysis to add

table_hints
    # used for styling hints like coloring or font.  The frontend currently doesn't do much with table_hints

column_ordering
    Allows a custom ordering of columns

    .. code-block:: python
    		
        class NumbersFirst(ColAnalysis):
            requires_summary = ['is_numeric']
        
            @staticmethod
            def column_ordering(summary_df):
	        # I know that this could be done in pure pandas on the summary_df
                col_dicts = []
                for i, col in enumerate(df.columns):
        	    col_facts = {
		        'name':col,
			'existing_order_score': i/len(df.columns)}
                    if summary_df[col]['is_numeric']:
        	        col_facts['numeric_boost'] = 2
        	    else:
                        col_facts['numeric_boost'] = 0
        	    col_facts['total_score'] = col_facts['existing_order_score'] + col_facts['numeric_boost']
                    return [cd['name'] for cd in sorted(col_dicts, key=lambda x: x['total_score'])]

    
summary_stats_display
    a list of which rows from summary stats to display.  Currently only the last added summary_stats_set is used


multiple column_orderings and summary_stats_facts can be added.  Then the UI allows the user to toggle through the different column orderings to see the view of the table they want.

Order of Operations
===================


The pluggable analysis framework runs different functions on analysis functions in a specific order.  First the DAG for all of the analysis objects and verifies that all of the needed facts can be computed. once all of the analysis objects are ordered the computations start.

1. Compute the order of analysis objects.  This builds a DAG and makes sure all of the facts can be computed.
2. Run all of the ``summary`` methods and build the ``summary_df``
3. extract table_hints from the ``summary_df``

