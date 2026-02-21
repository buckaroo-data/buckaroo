import marimo

__generated_with = "0.12.8"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        # Heuristic based auto cleaning
        We deal with data cleaning all the time as data scientists.  Most of it is repetitive doing the same thing over and over again

        Buckaroo proposes some heurstic based cleaning techniques that can be toggled through
        """
    )
    return


@app.cell
def _():
    #imagine a dataframe as follows
    import marimo as mo
    import pandas as pd
    import re
    dirty_df = pd.DataFrame({'probably_int': [10, 'a', 20, 30, "3,000"],
                             'mostly_us_dates': ["07/17/1982", "17/7/1983", "12/14/1991", "12/28/1996", "4/15/2024"],
                             'probably_bool': [True, "True", False, "No", "False"]
                            })
    dirty_df
    return dirty_df, mo, pd, re


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        From a quick eyeball we can tell the cleaned types from each column.  To clean this though, in regular pandas we have to manually scan each column, and then type from memory, stack overflow or LLM the correct transformation for each column.  The transforms are fairly limited and the fracs are pretty obvious, but we do the same rote work.

        More importantly, in this case the transforms are obvious.  What about actual large datasets.  Or datasets where the edge cases aren't visible via `df.head()`
        """
    )
    return


@app.cell
def _():
    return


@app.cell
def frac():
    def frac(f):
        """No Op for now.  This denotes that the function produces a 0-1 rating for a series that's passed in"""
        return f
    return (frac,)


@app.cell
def _(frac, pd, re):
    # Here is what I would like configuring a frac system to look like
    digits_and_period = re.compile(r'[^\d\.]')

    @frac
    def measure_int_parse(ser):
        null_count =  (~ ser.apply(pd.to_numeric, errors='coerce').isnull()).sum()
        return {'int_parse_fraction': null_count / len(ser)}

    @frac
    def measure_strip_int_parse(ser):
        stripped = ser.str.replace(digits_and_period, "", regex=True)
        int_parsable = ser.astype(str).str.isdigit() #don't like the string conversion here, should still be vectorized
        parsable = (int_parsable | (stripped != ""))
        return {'strip_int_parse_fraction': parsable.sum() / len(ser)}

    TRUE_SYNONYMS = ["true", "yes", "on", "1"]
    FALSE_SYNONYMS = ["false", "no", "off", "0"]
    BOOL_SYNONYMS = TRUE_SYNONYMS + FALSE_SYNONYMS

    @frac
    def f_str_bool(ser):
        #dirty_df['probably_bool'].str.lower().isin(BOOL_SYNONYMS)
        matches = ser.str.lower().isin(BOOL_SYNONYMS)
        return {'str_bool_fraction': matches.sum() / len(ser)}

    frac_measures = [measure_int_parse, measure_strip_int_parse, f_str_bool]
    return (
        BOOL_SYNONYMS,
        FALSE_SYNONYMS,
        TRUE_SYNONYMS,
        digits_and_period,
        f_str_bool,
        frac_measures,
        measure_int_parse,
        measure_strip_int_parse,
    )


@app.cell
def _(dirty_df, frac_measures, pd):
    pd.DataFrame({k: {m.__name__: list(m(dirty_df[k]).values())[0]  for m in frac_measures}  for k in dirty_df.columns})
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        Ok, this is looking pretty good.  We have 3 fracs, applied to 3 columns (but they are only made for two of the columns),  and we can see how frequently they get the right answer.

        Let's add more fracs
        """
    )
    return


@app.cell
def _(dirty_df, frac, frac_measures, pd):
    @frac
    def f_us_dates(ser):
        parsed_dates = pd.to_datetime(ser, errors='coerce', format="%m/%d/%Y")
        return {'us_date_fraction': (~ parsed_dates.isna()).sum() / len(ser)}

    @frac
    def f_euro_dates(ser):
        parsed_dates = pd.to_datetime(ser, errors='coerce', format="%d/%m/%Y")
        return {'us_date_fraction': (~ parsed_dates.isna()).sum() / len(ser)}
    more_fracs = frac_measures + [f_us_dates, f_euro_dates]
    pd.DataFrame({k: {m.__name__: list(m(dirty_df[k]).values())[0]  for m in more_fracs}  for k in dirty_df.columns})
    return f_euro_dates, f_us_dates, more_fracs


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        Things get interesting here.  Every row from mostly_us_dates parses as a number, even though the best date parsing only gets 0.8.  But we know that these are dates from looking at the data.  How should we resolve this?

        That's an open question.
        Either way, let's start writing some transform functions.
        """
    )
    return


@app.cell
def transform():
    def transform(frac):
        """Pair a transform function that actually cleans a series with the frac. used as a decorator """
        def dec(f):
            return f
        return dec
    return (transform,)


@app.cell
def _(
    FALSE_SYNONYMS,
    TRUE_SYNONYMS,
    digits_and_period,
    f_euro_dates,
    f_str_bool,
    f_us_dates,
    measure_int_parse,
    measure_strip_int_parse,
    pd,
    reg_parse,
    transform,
):
    @transform(measure_int_parse)
    def regular_int_parse(ser):
        return ser.apply(pd.to_numeric, errors='coerce')

    @transform(measure_strip_int_parse)
    def strip_int_parse(ser):
        _reg_parse = ser.apply(pd.to_numeric, errors='coerce')
        _strip_parse = ser.str.replace(digits_and_period, "", regex=True).apply(pd.to_numeric, errors='coerce')
        _combined = reg_parse.fillna(_strip_parse)
        return _combined

    @transform(f_str_bool)
    def t_str_bool(_ser):
        _int_sanitize = _ser.replace(1, True).replace(0, False) 
        _real_bools = _int_sanitize.isin([True, False])
        _boolean_ser = _int_sanitize.where(_real_bools, pd.NA).astype('boolean')    
        _trues = _ser.str.lower().isin(TRUE_SYNONYMS).replace(False, pd.NA).astype('boolean')
        _falses =  ~ (_ser.str.lower().isin(FALSE_SYNONYMS).replace(False, pd.NA)).astype('boolean')
        _combined = _boolean_ser.fillna(_trues).fillna(_falses)    
        return _combined

    @transform(f_us_dates)
    def t_us_dates(ser):
        return pd.to_datetime(ser, errors='coerce', format="%m/%d/%Y")

    @transform(f_euro_dates)
    def t_euro_dates(ser):
        return pd.to_datetime(ser, errors='coerce', format="%d/%m/%Y")
    # t_str_bool(pd.Series(["asdf", True, "True", "1", 0, None, 1]))
    return (
        regular_int_parse,
        strip_int_parse,
        t_euro_dates,
        t_str_bool,
        t_us_dates,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        Side note.  These functions are tricky to write.  So many edge cases.
        I see why I and most people punt on writing this stuff.  It's tricky and shouldn't have to be repeated.  The `t_str_bool` was one of the ahrdest to write.  Look at the commented out mini test case
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        Now to write the syntax for the heuristic class.

        The idea is that when each matching frac is the heighest percentage, apply that transform function to that column.

        I decied to leverage JLisp to create a simple, flexible syntax for writing heuristics.
        It looks like this
        ```python
        l_rules = {  #JLisp version
            't_str_bool':         [s('m>'), .7],
            'regular_int_parse':  [s('m>'), .9],
            'strip_int_parse':    [s('m>'), .7],
            'none':               [s('none-rule')],
            't_us_dates':         [s('primary'), [s('m>'), .7]]},
    
        l_rules_scheme = { #scheme version.  They are very close
            't_str_bool':         '(m> .7)',
            'regular_int_parse':  '(m> .8)',
            'strip_int_parse':    '(m> .9)',
            'none':               '(none-rule)',
            't_us_dates':         '(primary (m> .7))'}
        ```
        There are a couple of simple primitives.  Notablly `m>` which tests if the relevant measure is greater than a value.  A basic lisp is available, and this language is extensible, so I won't be limited.

        """
    )
    return


@app.cell
def _():
    return


@app.cell
def _(regular_int_parse, strip_int_parse, t_str_bool, t_us_dates):
    # base case heuristic is if this measure is the most popular of all heuristics, and it's frac is above value, then use this transform
    heuristic = {t_str_bool:.7, regular_int_parse:.9, strip_int_parse:.7}
    # but to make dates work we have to add other condtions and syntax
    # because in our example mostly_us_dates always parses as strip_int_parse at frac=1
    heuristic2 = {t_str_bool:('greatest', 'and', ('gt', .7)), 
                  regular_int_parse:('greatest', 'and', ('gt', .9)),
                  strip_int_parse:('greatest', 'and', ('gt', .7)), 
                  t_us_dates:('only', ('gt', .6))}
    # so we introduce the 'only' operator.  meaning, use this transform if and only if the frac , then the other conditional
    return heuristic, heuristic2


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Multiple heuristics.

        Writing `transforms` and `fracs` is tricky and will be done infrquently.  Writing heuristic sets will be done regularly, and lets you toggle through different views
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Multi Column operations

        ### Splitting columns
        I frequently see cleanings where two values are jammed into a single string column. `"2020 - 2024"`.  A `frac` function and a transform that returns two columns is needed here.  This will also mean the transform runtime is more complex than a list comprehension

        ### Combining columns

        I can look at a dataset and see "start_station_latitude", and "start_station_longitude" and know that those are lat/long, and should be treated as a single coordinate.  I'm at a loss to think of how write a `frac` to detect this.

        Treating lat/long as a single tuple allows much easier downstream work.  What's the geographic center,  what's the geographic center over time
        """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Heuristic syntax for splitting columns
        This is a place where we want to depend on extra fracs

        from experience multiple numbers shoved into a single field would have a separating character. probably one of `,:-|;`
        what would those rules look like?  Let's try this syntax on for size
        ```lisp
            (and 
                (> (frac-get 'char_int') .75)    ; we want mostly integers characters
                (< (frac-get 'char_letter') .1)  ; we don't want many letters
                                                                                 ; not 100% sure on this syntax for a list of characters
                (between (/ (sum (apply (lambda (chr) (dict-get char-freqs chr)) ',:-| ))
                            (dict-get total-chars)) ; the fraction of split characters
                         .01 .2))
        ```
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Row level transforms

        Dropping duplicate rows is obvious.  Drpping rows with nulls in a colum is obvious.  The `frac` and row level `heuristic` s for these are harder to figure out.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Buckaroo specific concerns
        Up to this point, I have described a general system. Below is how Buckaroo approaches the problem. I'm happy to collaborate with anyone on all of it, but the general autocleaning discussion is much more broadly applicable.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## How Autocleaning fits with a low code UI

        These are nice examples of a toy auto cleaning system. But they will be clunky to use. I don't think any single auto-cleaning system can correctly clean all datasets. It is also clear that auto-cleaning needs fine-grained overrides in a UI, or code export. The Buckaroo autocleaning system/low-code UI is capable of offering both.

        ### Commands in Buckaroo

        Commands are equivalent to `transform`s above.  They are built by writing classes that implement two functions.  `transform` takes a dataframe and returns a modified dataframe (ignore the other args for now). `transform_to_py` takes the same arguments and returns a string with the equivalent python code.

        ```python
        class FillNA(Command):
            command_default = [s('fillna'), s('df'), "col", 8]
            command_pattern = [[3, 'fillVal', 'type', 'integer']]

            @staticmethod 
            def transform(df, col, val):
                df.fillna({col:val}, inplace=True)
                return df

            @staticmethod 
            def transform_to_py(df, col, val):
                return "    df.fillna({'%s':%r}, inplace=True)" % (col, val)

        ```

        ### A quick note about JLisp
        Buckaroo represents lowcode programs as [JLisp](https://github.com/buckaroo-data/buckaroo/blob/main/buckaroo/jlisp/lispy.py) which is a port of Peter Norvig's Lispy.py, that can interpret JSON Flavored lisp instead of paren lisp.
        ```lisp
        (fillna df "col_with_nas" 8)
        ```
        becomes
        ```json
        [{'symbol': 'fillna'}, {'symbol':'df'}, 'col_with_nas', 8]
        ```

        I created JLisp because I was going to write some type of interpreter that no one understood.  At least I could build on a solid foundation that there is a good general understanding of.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## The lowcode UI in Buckaroo

        ![Lowcode image](public/Lowcode-UI.png)
        ### Operation Detail editor
        The lowcode UI in buckaroo is a specialized editor of operations (buckaroo term for JLisp programs).  Since all current commands operate on columns, first a column must be clicked, then an operation can be performed on that column.  Commands can take other arguments (enum, another column name, an int).

        ### Operation timeline editor
        The order of operations can also be seen. This concept is stolen from [CAD](https://www.youtube.com/watch?v=o5NsPOcXLho&t=202s) [software](https://help.autodesk.com/view/fusion360/ENU/?guid=ASM-USE-TIMELINE).
        Operations can be clicked on to get a detail view where the arguments can be editted. Operations can also be deleted (and eventually drag and drop reordered)

        ### It's ugly
        Yep.  This was the first part of buckaroo I built, and I haven't revisited it because this is all an advanced hard to explain concept. The concepts are key at this point. Styling updates coming soon.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## The lowcode UI and autocleaning together

        In Buckaroo, autocleaning doesn't directly modify the dataframe, instead it generates `operation`s for the lowcode UI.

        These operations are tagged from autocleaning, so they look like this
        ```json
        [{'symbol': 'strip_int_parse', 'meta':'autocleaning'}, {'symbol':'df'}, 'probably_int']
        ```

        Tagging in this way allows the UI to show which operations come from autocleaning.  Then when the user selects a different autocleaning method, all previous `operations` with `'meta':'autocleaning'` are removed from the operations, and new autocleaning operations are prepended to the user created operations.
        ### Coming soon
        If a user wants to retain a particular autocleaning operations, they can click a "promote to permanent" button
        ## Exporting functioning code is key
        Buckaroo seeks to have a good UX for cleaning data, but at some point you will want to write code.  I don't expect users to ever edit JLisp by hand, almost never write `frac` or `command`s, rarely write heuristics.  But I do expect them to regularly write python code.  Having that escape hatch is key.
        """
    )
    return


@app.cell(hide_code=True)
def _():
    #Also, our nested dictionary comprehension to dataframe is cute, but watch what happens when we have an error measure
    #error_measures = measures + [lambda x: 1/0] + [us_dates]
    #pd.DataFrame({k: {m.__name__: list(m(dirty_df[k]).values())[0]  for m in error_measures}  for k in dirty_df.columns})
    # what column threw the error. what happened to the rest of the code?
    return


if __name__ == "__main__":
    app.run()
