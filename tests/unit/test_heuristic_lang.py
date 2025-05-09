from buckaroo.auto_clean.heuristic_lang import eval_heuristic_rule, eval_heuristics, get_top_score
from buckaroo.jlisp.lisp_utils import s

"""
This isn't heuristic lang but it is auto_clean.


So the UI has added a concept of "preserve" where a cleaning operation as denoted by
{'symbol':'func_name', 'meta':{'auto_clean':True, 'clean_strategy':'aggressive'}}
becomes
{'symbol':'func_name', 'meta':{'clean_strategy':'aggressive'}}

this means that when the next set of auto_cleaning operations is
generated, that particular operation won't be removed (only 'auto_clean':True operations are removed)

BUT the enxt cleaning strategy will try to do something different to the same column.  We want to filter those operations out somehow... I think


Maybe an 'meta': {prevent_cleaning:True}... but that is on the operation, we want it on the column.  think about this a bit


Also add a meta param that has the deicding _frac's from heuristics that chose a cleaning strategy for a given column.  Then that meta_param can be written out in python code as a comment.  call it "reasoning"


The operation detail viewer can show these comments


"""


l_rules = {
    't_str_bool':         [s('f>'), .7],
    'regular_int_parse':  [s('f>'), .9],
    'strip_int_parse':    [s('f>'), .7],
    'none':               [s('none-rule')],
    't_us_dates':         [s('primary'), [s('f>'), .7]]}

def test_get_top_score():
    probably_bool= {
        't_str_bool': .8, 'regular_int_parse': .2, 'strip_int_parse': .3, 't_us_dates': 0}
    
    get_top_score(l_rules, probably_bool)

def test_eval_heuristics():
    col_scores = dict(
        probably_bool= {
            't_str_bool': .8, 'regular_int_parse': .2, 'strip_int_parse': .3, 't_us_dates': 0},
        # no_changes = {
        #     't_str_bool': 0, 'regular_int_parse': 0, 'strip_int_parse': 0, 't_us_dates': 0},
        probably_dates = {
            't_str_bool': .8, 'regular_int_parse': .95, 'strip_int_parse': 0, 't_us_dates': .71})
    res = eval_heuristics(l_rules, col_scores)
    assert res== dict(probably_bool='t_str_bool', probably_dates='t_us_dates')

def test_eval_heuristics_no_match():
    col_scores = dict(
        no_changes = {
            't_str_bool': 0, 'regular_int_parse': 0, 'strip_int_parse': 0, 't_us_dates': 0})
    res = eval_heuristics(l_rules, col_scores)
    print("res", res)
    assert res== dict(no_changes='none')
    
    

def test_macro_behaviour_rule():
    #verify that macros work from scheme and jlisp
    assert eval_heuristic_rule([s('f>'), .7], .6) == False
    assert eval_heuristic_rule('(f> .7)', .6) == False

    

    assert eval_heuristic_rule([s('if'), 4, s('measure'), 9], 3) == 3
    assert eval_heuristic_rule([s('f>'), .7], .8) == .8


    
def test_none_null():
    assert eval_heuristic_rule([s('null?'), s('measure')], []) == True
    assert eval_heuristic_rule([s('null?'), [s('f>'), .7]], .9) == False
    assert eval_heuristic_rule([s('none?'), s('measure')], None) == True


def test_heuristic_rule():
    assert eval_heuristic_rule([s('begin'),
                                [s('display'), s('measure')],
                                s('measure')],
                                .7) == .7
    assert eval_heuristic_rule('(f> .7)', .8)  == .8
    assert eval_heuristic_rule('(f> .7)', .5)  == False
    assert eval_heuristic_rule([s('f>'), .7], .8) == .8
    assert eval_heuristic_rule([s('f>'), .7], .6) == False
    assert eval_heuristic_rule([s('primary'), [s('f>'), .7]], .6) == False
    assert eval_heuristic_rule([s('primary'), [s('f>'), .7]], .8) == 80


def test_timing(): # noqa: E712
    import time
    start_time = time.perf_counter()
    for i in range(100):
        assert eval_heuristic_rule([s('f>'), .7], .6) == False
        assert eval_heuristic_rule([s('primary'), [s('f>'), .7]], .6) == False
        assert eval_heuristic_rule([s('primary'), [s('f>'), .7]], .8) == 80
        assert eval_heuristic_rule([s('primary'), [s('f>'), .7]], .6) == False  
        assert eval_heuristic_rule([s('f>'), .7], .6) == False  # noqa: E712
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    print(f"Function execution time: {execution_time:.4f} seconds")
    # 20 columns, 5 rules = 100
    # 5 strategies (sets of rules)
    # less than 10ms on my machine, this is fast enough
