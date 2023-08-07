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

default_cleaning_instructions

    If a column has 5000 rows, and 3000 of them are parseable as an integer, and the other 2000 rows are "n/a", it was probably the intention of the original data for this to be an integer column with nulls.  DefaultCleaningInstructions.  The transform to integer can be coded as a custom command for the low-code-ui, then you can write a ColAnalysis that suggests this transform be automatically executed on load of a dataframe.

    It would look like this

    .. code-block:: python
		    
        def safe_int(x):
            try:
                return int(x)
            except:
                return np.nan
        
        class IntClean(ColAnalysis):
            provided_summary = [
                'cleanable_int']
        
            @staticmethod
            def summary(sampled_ser, summary_ser, ser):
                counts = sampled_ser.value_counts()
        	parseable = 0
        	for val in counts.index:
                if safe_int(val) not np.nan:
        	        parseable += 1
        
        	mostly_parseable = parseable / len(counts) > 0.95
        	return {'cleanable_int': mostly_parseable}
        
            @staticmethod
            def cleaning_instruction(summary_ser, col_name):
                if summary_ser.loc['cleanable_int'] == False:
        	    return None
        	return ['safe_int', col_name]


    Then this clean_int will be automatically loaded into the instruction viewer in the low code ui, and it will already have been executed for the loaded dataframe
    
    I'm still figuring out how to toggle through different cleanings. I'm worried about modifying the default columns.  I guess I can make the returned cleaning instructions do a column rename by convention. so for the above cleaning instruction first copy the original column name to "_orig"
    
summary_stats_set
    a list of which rows from summary stats to display.  Currently only the last added summary_stats_set is used


multiple column_orderings and summary_stats_facts can be added.  Then the UI allows the user to toggle through the different column orderings to see the view of the table they want.

Order of Operations
===================


The pluggable analysis framework runs different functions on analysis functions in a specific order.  First the DAG for all of the analysis objects and verifies that all of the needed facts can be computed. once all of the analysis objects are ordered the computations start.

1. Compute the order of analysis objects.  This builds a DAG and makes sure all of the facts can be computed.
2. Run all of the ``summary`` methods and build the ``summary_df``
3. Run all of the ``cleaning_instructions`` methods and get the list of interpreter instructions
4. Run the interpreter and produce a new "cleaned" dataframe
5. Run all of the ``summary`` methods and build the ``summary_df`` for the cleaned dataframe.
6. Run all of the ``table_hints`` methods and build the table_hints dictionary
7. Run all of the ``col_ordering`` methods and produce the different col_orderings.

Porting to polars
=================

I would really like to be able to run these computations in lazy polars, there should be very significant speed increases.  I think this stackoverflow answer might be the key... but I'm not sure  https://stackoverflow.com/a/76560342


For now I'm just focussing on writing the framework and making sure it works... I can make it fast later... I think.

After further thought, I think I can make all of the base series calcs lazy with pl.struct.  Then do all the other calcs in pure python (they should be fast).
