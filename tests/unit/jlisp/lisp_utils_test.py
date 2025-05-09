from buckaroo.jlisp.lisp_utils import (
    merge_ops, format_ops, lists_match, split_operations, s, sA, ops_eq
                                       )


def test_split_operations():

    full_ops = [
        [{"symbol":"dropcol", "meta":{"auto_clean":True}},{"symbol":"df"},"starttime"],
        [{"symbol":"dropcol"},{"symbol":"df"},"starttime"],
    ]

    EXPECTED_cleaning_ops = [
        [{"symbol":"dropcol", "meta":{"auto_clean":True}},{"symbol":"df"},"starttime"]]
    
    EXPECTED_user_gen_ops = [
        [{"symbol":"dropcol"},{"symbol":"df"},"starttime"]]

    cleaning_ops, user_gen_ops = split_operations(full_ops)

    assert EXPECTED_cleaning_ops == cleaning_ops
    assert EXPECTED_user_gen_ops == user_gen_ops

def test_lists_match():

    assert lists_match(["a", "b"], ["a", "b"])
    assert lists_match([["a", "b"]], [["a", "b"]])
    assert not lists_match(["a", "b"], ["a", "b", "c"])
    assert not lists_match([["a", "b"]], [["a", "b", "c"]])

    
SAFE_INT_TOKEN = [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}]


def test_format_ops():
    """
    make sure that format_ops joins the correct column names to ops
    """
    column_meta = {
        'a': {'cleaning_ops':SAFE_INT_TOKEN },
        'b': {'cleaning_ops': [
            {'symbol': 'replace_dirty', 'meta':{'auto_clean': True}},
            {'symbol': 'df'}, '\n', None]}}

    expected_ops = [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'a'],
        [{'symbol': 'replace_dirty', 'meta':{'auto_clean': True}}, {'symbol': 'df'}, 'b', '\n', None]]
    assert format_ops(column_meta) == expected_ops



def test_merge_ops():
    existing_ops = [
        [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, 'a'],
        [{'symbol': 'usergen'}, 'foo_column']
    ]

    cleaning_ops = [
        [{'symbol': 'new_cleaning', 'meta':{'auto_clean': True}}, 'a']]

    expected_merged = [
        [{'symbol': 'new_cleaning', 'meta':{'auto_clean': True}}, 'a'],
        [{'symbol': 'usergen'}, 'foo_column']
    ]
    print( merge_ops(existing_ops, cleaning_ops))
    print("@"*80)
    assert merge_ops(existing_ops, cleaning_ops) == expected_merged

def test_merge_ops_conflict():
    """
    When a user clicks preserve, on an autoclean operation. we don't want subsequent cleaning to do a different clean on that column
    """

    gen_ops =  [
        [sA('noop2', clean_col='c') , s('df'), 'c']]

    user_ops  = [
        [s('noop2', clean_col='c') , s('df'), 'c']]

    merged_ops = merge_ops(user_ops, gen_ops)
    assert ops_eq(merged_ops, user_ops)

def test_merge_ops_conflict2():
    gen_ops =  [
        [sA('noop', clean_col='a') , s('df'), 'a'],
        [sA('noop', clean_col='b') , s('df'), 'b'],
        [sA('noop', clean_col='c') , s('df'), 'c']]

    #a user 'preserved' the op on b.
    # these are the ops that the frontend will send back to buckaroo
    user_ops =  [
        [sA('noop', clean_col='a') , s('df'), 'a'],
        [s('noop', clean_col='b') , s('df'), 'b'],
        [sA('noop', clean_col='c') , s('df'), 'c']]


    expected_merge_ops = [
        [sA('noop', clean_col='a') , s('df'), 'a'],
        [sA('noop', clean_col='c') , s('df'), 'c'],
        #this should be moved to the end because user_ops come after clean_ops
        [s('noop', clean_col='b') , s('df'), 'b']]


    merged_ops = merge_ops(user_ops, gen_ops)
    assert ops_eq(merged_ops, expected_merge_ops)
