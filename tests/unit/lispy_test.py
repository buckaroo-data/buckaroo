from buckaroo.jlisp.lisp_utils import split_operations, lists_match

def test_split_operations():

    full_ops = [
        [{"symbol":"dropcol", "meta":{"precleaning":True}},{"symbol":"df"},"starttime"],
        [{"symbol":"dropcol"},{"symbol":"df"},"starttime"],
    ]

    EXPECTED_cleaning_ops = [
        [{"symbol":"dropcol", "meta":{"precleaning":True}},{"symbol":"df"},"starttime"]]
    
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
    
