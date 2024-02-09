.. _data_flow:

Data Flow through Buckaroo
===========================


Buckaroo is extensible.  The architecture of Buckaroo is crafted to allow specific points of composable extensibility in an opinionated manner.  It was designed this way based on experience from writing many adhoc analysis pipelines.  Previous "simpler" attempts at extensibility ran into bugs that couldn't be cleanly accomodated. The following will be addressed below:

Buckaroo aims to allow highly opionated configurations to be toggled by users.  With buckaroo, you can add a cleaning_method of "interpret int as milliseconds from unix epoch", and it will look at a column of ints, and decide that values map to datetimes in the past year (as opposed to centered around 1970) and we should treat this column as a datetime.  That is a highly opinionated view of your data, the cost for that highly opinonated view is less when multiple opinions can be quickly cycled through.

This approach is different than most tools which aim to be a generic tool that is customizable with bespoke configuration.  It would be a bad thing if a generic table tool displayed integers as dates because it assumes that those integers are milliseconds from the unix epoch.  Normally this would require custom code to be written and called based on manual inspection of the data.

This document describes the multiple ways of extending bucakroo to add your own toggable opinons.






#. understand the dataflow through Buckaroo
#. quick start to extending buckaroo
#. description of extension points


Customization points of Buckaroo
--------------------------------


#. Sample_method
   Used to specify conditions for downsampling dataframe and method of sampling.  Example alternatives include sampling in chunks,  only showing first and last row, random sampling, and limiting number of columns.  Returns  sampled df
#. Cleaning_method
   recieves sampled_dataframe Used to control how dataframes are cleaned before summary stats are run.  Examples include special parsing rules for unique date formats, removing strings from primarily numeric columns.  Returns cleaned_df and cleaned_summary_dict
#. Post_processing_method
   recieves entire cleaned dataframe. Used to perform multi-column operations, like adding a running_diff column, or combining a latitude and longitude column into a single lat/long column.  returns processed_df and processed_summary_dict
#. Analysis_klasses
   recieves individual columns from processed_df.  Individual column level analysis klasses used to fill out summary_stats.  examples include mean, median, min, max, and complex results like histograms.  Each class returns a summary_dict about a single column
#. style-method
   recieves col_name, col_summary_dict, default_config.  Takes a column_summary_dict and returns the column_config for that column.  Examples include formatting a datetime as time only if the min/max are within a single day, conditionally turning on tooltips and color_maps based on other info in summary_dict



.. raw:: html

    <style> 
            .dataflow-result {color:blue}
            .dataflow-arg {color:purple}
            .class-state {color:green}
            .ui-variable {color:orange}
            .tuple-result {color:red}
            .tuple-param {color:#d4706e} /* a darker pink */
            .tuple-param {color:gray} /* a darker pink */
    </style>


.. role:: dataflow-result
.. role:: dataflow-arg
.. role:: class-state
.. role:: ui-variable
.. role:: tuple-param
.. role:: tuple-result

   
Full Flow
---------

Starting with ``raw_df`` data flows through buckaroo as follows.  If one of the values on the right side of equals changes, all steps below that are executed

The final result of `widget` is what is displayed to the user.



+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|Destination                                   |args                                                                                                                         |
+==============================================+=============================================================================================================================+
|:dataflow-result:`sampled_df`                 |:class-state:`raw_df`, :ui-variable:`sample_method`                                                                          |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|:dataflow-result:`cleaned`                    |:dataflow-arg:`sampled_df`, :ui-variable:`sample_method`, :ui-variable:`cleaning_method`, :ui-variable:`lowcode_ops`         |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|                                              |:tuple-result:`cleaned_df`, :tuple-result:`cleaned_sd`, :tuple-result:`generated_code`                                       |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|:dataflow-result:`processed`                  |:dataflow-arg:`cleaned_df`, :ui-variable:`post_processing_method`                                                            |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|                                              |:tuple-result:`processed_df`, :tuple-result:`processed_sd`                                                                   |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|:dataflow-result:`summary_sd`                 |:dataflow-arg:`processed_df`, :class-state:`analysis_klasses`                                                                |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|:dataflow-result:`merged_sd`                  |:tuple-param:`cleaned_sd`, :dataflow-arg:`summary_sd`, :tuple-param:`processed_sd`                                           |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+
|:dataflow-result:`widget`                     |:tuple-param:`processed_df`, :dataflow-arg:`merged_sd`, :ui-variable:`style_method`, :tuple-param:`generated_code`           |
+----------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------+

.. graphviz:: dataflow.dot



Glossary
........

#. :dataflow-result:`dataflow-result`    are the result of a step. updates to this variable trigger steps that watch the variable as a dataflow arg
#. :dataflow-arg:`dataflow-arg`          a dataflow-result used as a function argument. updates to this cause the current step to execute
#. :ui-variable:`UI-Variable`            are specified in the UI, and can be changed interactively. updates to this cause the current step to execute
#. :class-state:`class-state`            are defined at class instantiation time, these can be customized, but not interactively
#. :tuple-result:`named-tuple-result`    Some results return as a tuple, the tuple is what is watched, the sub parts of the tuple can be referenced later
#. :tuple-param:`tuple-param`            read this from the a named-tuple-result. do not watch this vriable (setting this named-tuple-result will not trigger this step)


.. graphviz:: glossary.dot


Quick Start to extending Buckaroo
---------------------------------

In this exercise we are going add a custom coloring method to Buckaroo.  We will take an OHLCV dataframecolor and Volume based on the change from the previous day.

First we need to craft the column config that will enable this conditonal coloring.

We want to use `ColorFromColumn`, we want the config for the volume column to look like

.. code-block:: python
    
    volume_config_override = {
        'color_map_config' : {
	    'color_rule': 'color_from_column',
            'col_name': 'Volume_colors'}}


Using this in Buckaroo will look like this
 
.. code-block:: python

    df = get_ohlcv("IBM")
    df['Volume_colors'] = 'red'
    BuckarooWidget(df, override_column_config={'Volume': volume_config_override})

This is a nice start.  But now our analysis depends on remembering and typing specific config lines each time we want this display.


Buckaroo provides built in ways of handling this.

First we want to use a `post_processing_function` to add the `volume_colors` column all of the time.  And to make it condtional on change.  we need to use `post_processing_function` because we specifically need to operate on the whole dataframe, not just a single column.


.. code-block:: python

    def volume_post(df):
        if 'Volume' not in df.columns:
	    return [df, {}]
	df['Volume_colors'] = 'red'  # replace with actual red/green based on diff
	extra_summary_dict = {
            'Volume' : {
	        'column_config_override': {
	            'color_map_config' :
		        {'color_rule': 'color_from_column',
			 'col_name': 'Volume_colors'}}},
            'Volume_colors' : {
	        'column_config_override': {
		    'displayer': 'hidden'}}}
	return [df, extra_summary_dict]
    
     class OHLVCBuckarooWidget(BuckarooWidget):
         post_processing_function=volume_post
    OHLVCBuckarooWidget(get_ohlcv("IBM"))


Now when you instantiate `OHLVCBuckarooWidget` there will be a UI toggable function of `volume_post` so you can turn on and turn off this feature interactively.  `OHLVCBuckarooWidget` has your own opinions baked in, that the user can turn on or off.

What if we want to switch between red/green colors map and a color map based on size of diff to previous day?  In this case we want to add two "style_methods" which are togglable in the UI.  style_method takes a summary_dict and returns the column config.


.. code-block:: python

    def volume_post(df):
        if 'Volume' not in df.columns:
	    return [df, {}]
	df['Volume_colors'] = 'red'  # replace with actual red/green based on diff
	df['Volume_diff'] = df['Volume'].diff()
	extra_summary_dict = {
            'Volume_colors' : { 'column_config_override': { 'displayer': 'hidden'}},
            'Volume_diff' : { 'column_config_override': { 'displayer': 'hidden'}}}
	return [df, extra_summary_dict]

     def volume_style_red_green(col_name, col_summary_dict, default_config):
         if col_name == 'Volume':
	     return {'override': {
	            'color_map_config' : {'color_rule': 'color_from_column', 'col_name': 'Volume_colors'}}}
	 return {}

     def volume_style_color_map(col_name, col_summary_dict, default_config):
         if col_name == 'Volume':
	     return {'override': {
	            'color_map_config' : {'color_rule': 'color_map', 'map_name': 'BLUE_TO_YELLOW',
		                          'val_column': 'Volume_diff'}}}
	 return {}
	 
     class OHLVCBuckarooWidget(BuckarooWidget):
         post_processing_function=volume_post
	 style_methods=[volume_style_red_green, volume_style_color_map]
    OHLVCBuckarooWidget(get_ohlcv("IBM"))


With this implementation, the frontend can cycle through three style_methods `volume_style_red_green`, `volume_style_color_map` and `default`



   



