import marimo

__generated_with = "0.12.8"
app = marimo.App(width="medium")


@app.cell
def _():
    from buckaroo.jlisp.lisp_utils import s
    from buckaroo.jlisp.lispy import make_interpreter
    jl_eval, sc_eval = make_interpreter()
    from buckaroo.auto_clean.heuristic_lang import eval_heuristic_rule, eval_heuristics, get_top_score
    return (
        eval_heuristic_rule,
        eval_heuristics,
        get_top_score,
        jl_eval,
        make_interpreter,
        s,
        sc_eval,
    )


@app.cell
def _(s):
    l_rules = {
        't_str_bool':         [s('m>'), .7],
        'regular_int_parse':  [s('m>'), .9],
        'strip_int_parse':    [s('m>'), .7],
        'none':               [s('none-rule')],
        't_us_dates':         [s('primary'), [s('m>'), .7]]}
    return (l_rules,)


@app.cell
def _():
    l_rules_scheme = {
        't_str_bool':         '(m> .7)',
        'regular_int_parse':  '(m> .8)',
        'strip_int_parse':    '(m> .9)',
        'none':               '(none-rule)',
        't_us_dates':         '(primary (m> .7))'}
    return (l_rules_scheme,)


@app.cell
def _(eval_heuristics, l_rules):
    col_scores = dict(
            probably_bool= {
                't_str_bool': .8, 'regular_int_parse': .2, 'strip_int_parse': .3, 't_us_dates': 0},
            no_changes = {
                't_str_bool': 0, 'regular_int_parse': 0, 'strip_int_parse': 0, 't_us_dates': 0},
            probably_dates = {
                't_str_bool': .8, 'regular_int_parse': .95, 'strip_int_parse': 0, 't_us_dates': .71})
    res = eval_heuristics(l_rules, col_scores)
    res
    return col_scores, res


@app.cell
def _():
    import marimo as mo
    return (mo,)


if __name__ == "__main__":
    app.run()
