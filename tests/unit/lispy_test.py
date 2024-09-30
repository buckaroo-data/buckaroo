from buckaroo.jlisp.lisp_utils import split_operations, lists_match
from buckaroo.jlisp.lispy import make_interpreter, s

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
    
def test_blank_interpreter():
    jlisp_eval, jlisp_local_eval = make_interpreter()
    assert jlisp_eval([s('+'), 3, 8]) == 11
    assert jlisp_eval([s('+'), s('a'), 8], {'a':5}) == 13

def test_add_func():
    jlisp_eval, jlisp_local_eval = make_interpreter()
    assert jlisp_eval([s('+'), 3, 8]) == 11
    assert jlisp_eval([s('+'), s('a'), 8], {'a':5}) == 13

    #assert jlisp_eval([s('always5')]) == 5


def test_scheme_macros():
    base_eval, lisp_eval = make_interpreter()

    
    lisp_eval("""(begin
    (define-macro and (lambda args 
       (if (null? args) #t
           (if (= (length args) 1) (car args)
               `(if ,(car args) (and ,@(cdr args)) #f)))))
    
    ;; More macros can also go here
    
    )""")
    assert lisp_eval("(+ 3 5)") == 8
    #verify that we can define a variable
    assert base_eval([s('begin'), [s('define'), s('foo'), 5], [s('+'), s('foo'), 1]]  ) == 6

    #verify that referencing a variable with an env passed in resolves properly
    assert base_eval([s('+'), s('foo'), 1], {'foo':20}) == 21

    #verify that the original env is untouched
    assert base_eval([s('+'), s('foo'), 1]) == 6


def test_functions():
    """
    verify that functions passed into the environment can be called
    """
    def always5():
        return 5

    def add5(num):
        return num+5

    _eval, _parse = make_interpreter()
    assert _eval([s('always5')], {'always5':always5, 'add5':add5} ) == 5

def test_assignment():
    """
    show assignment for defined variables
    """
    jl_eval, sc_eval = make_interpreter()
    assert sc_eval("(begin (define var 1) (set! var (* var 10)) var)") == 10
    jl_form = [s("begin"),
               [s("define"), s("var"), 2],
               [s("set!"), s("var"), [s("*"), s("var"), 10]],
               s("var")]
    assert jl_eval(jl_form) == 20

def test_assign_env():
    """
    verify that we can set a variable that was passed in"
    """
    jl_eval, sc_eval = make_interpreter()

    jl_form = [s("begin"),
               [s("set!"), s("var"), [s("*"), s("var"), 10]],
               s("var")]
    assert jl_eval(jl_form, {'var':3}) == 30
