import pytest
from buckaroo.jlisp.lisp_utils import s
from buckaroo.jlisp.lispy import make_interpreter, Symbol, isa



    
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

# def test_error_handle():
#     """
#     verify that functions passed into the environment can be called
#     """
#     def throw_error():
#         1/0
#         return "never reached"

#     _eval, _parse = make_interpreter()
#     with pytest.raises(UserFuncException) as _excinfo:
#         _eval([s('throw_error')], {'throw_error':throw_error} )
#         print(_excinfo)
#     print(_excinfo)
    
#     8/0

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


def test_other():
    jl_eval, sc_eval = make_interpreter()
    jl_eval([s('begin'), s('df')], {'df':5}) == 5 # pass in a variable and return it
    jl_eval([s('begin'), [s('define'), s('df2'), 8], s('df2')], {'df':5}) == 8 # define a variable
    def dict_get(d, key, default=None):
        return d.get(key, default)
    #pass in a defined function from python
    jl_eval([s('dict_get'), s('fruits'), 'apple'], {'dict_get': dict_get, 'fruits':{'apple':9}}) == 9 
    jl_eval([s('dict_get'), s('fruits'), 'pear', 99], {'dict_get': dict_get, 'fruits':{'apple':9}}) == 9
    jl_eval([s('>'), 4, 9]) # comparison

    jl_eval([s('begin'), 
             [s('define'), s('named_func'), [s('lambda'), [s('a')], 
                                             [s('+'), s('a'), 3]]],
             [s('named_func'), 10]
             ])
     # define a lambda, assign it to a variable 'named_func', then call it with an argument of 10

def test_lambda_no_args():
    """I don't know how to get a no arg lambda to work, punting for now """ 
    [s('begin'), 
            [s('define'), s('some_var'), 5],
            [s('define'), s('named_func'), [s('lambda'), [], #[s('unused')], 
                                                [s('+'), s('some_var'), 3]]],
            [s('named_func')]
        ]
    assert True

def test_macro2():
    jlisp_eval, sc_eval = make_interpreter()

    with pytest.raises(LookupError) as _excinfo:
        sc_eval("""(and 4 3)""")
    sc_eval("""
(begin
   (define-macro and (lambda args 
       (if (null? args) #t
           (if (= (length args) 1) (car args)
               `(if ,(car args) (and ,@(cdr args)) #f)))))
        
        (define-macro and (lambda args 
        (if (null? args) #t
           (if (= (length args) 1) (car args)
               `(if ,(car args) (and ,@(cdr args)) #f)))))
;; More macros can go here
)""")
    assert sc_eval("""(and 4 3)""") == 3
    assert sc_eval("""(> 3 5)""") == False
    assert sc_eval("""(and (> 3 5) 7)""") == False

    #make sure we can use the macros from jlisp too
    assert jlisp_eval([s('and'), 4, 3]) == 3
    assert jlisp_eval([s('and'), [s('>'), 3, 5], 7]) == False

    #assert sc_eval("""(and (> 3 5) 7)""") == False



def test_macro_rule():
    jlisp_eval, sc_eval = make_interpreter()

    with pytest.raises(LookupError) as _excinfo:
        sc_eval("""(and 4 3)""")
    sc_eval("""
(begin
   (define-macro and (lambda args 
       (if (null? args) #t
           (if (= (length args) 1) (car args)
               `(if ,(car args) (and ,@(cdr args)) #f)))))

;; More macros can go here

    ;; Rule basically lets us define a lambda with less syntax
    (define-macro rule (lambda args
        `(lambda unused ,@args)))

    ;; convience for defining a conditional that will be evaulated with measure passed n
    (define-macro rule-measure (lambda args
        `(lambda (measure) ,@args)))

    (define-macro m> (lambda operand
        `(> measure ,@operand)))

    (define-macro m< (lambda operand
        `(< measure ,@operand)))
)""")
    """(let ((a 1) (b 2)) (+ a b)n)"""
    assert sc_eval("""(let ((a (rule (> 3 5))) (b 2)) (a 8))""") == False
    assert sc_eval("""(let ((a (rule (< 3 5))) (b 2)) (a 8))""") == True

    
    assert sc_eval("""(let ((measure 2)) (> measure 8))""") == False
    # test a simple form of the m> macro
    assert sc_eval("""(let ((measure 2)) (m> 8))""") == False
    #make sure m> doesn't always return False
    assert sc_eval("""(let ((measure 2)) (m> 1))""") == True

    # can we pass an expression into m>
    assert sc_eval("""(let ((measure 2)) (m> (- 5 9)))""") == True

    #rule must be evaluated at a place where measure is defined
    assert sc_eval("""(let ((measure 2))
                           (let ((a (rule (m> 8))))  (a 'unused)))""") == False


    assert sc_eval("""(let ((a (rule-measure (m> 8))))  (a 2))""") == False


def test_lambda_arg_handling():
    jlisp_eval, sc_eval = make_interpreter()
    #try to define a lambda that takes no arguments

    # you must specify an argument that the lambda takes, but it isn't
    # necessary to pass that argument when you call the lambda
    assert sc_eval("""(let ((a (lambda foo (> 3 5)))) (a))""") == False
    assert sc_eval("""(let ((a (lambda foo (< 3 5)))) (a))""") == True

    # you can even pass args that the lambda doesn't have arguments for
    assert sc_eval("""(let ((a (lambda foo (< 3 5)))) (a 3))""") == True
    assert sc_eval("""(let ((a (lambda foo (< 3 5)))) (a 3 9))""") == True
def test_gensym():
    jlisp_eval, sc_eval = make_interpreter()
    assert sc_eval("""(gensym)""") == "GENSYM-0"
    #we get a unique one next time this is called
    assert sc_eval("""(let ((a (gensym))) a)""") == "GENSYM-1"
    assert sc_eval("""(begin

        (define  a 20)
    `,a)""") == 20
    assert sc_eval("""(begin
        (define  b (gensym))
    `,b)""") == Symbol("GENSYM-2")

    assert sc_eval("""(begin
        (define  b (gensym))
        (define b 20)
    `,b)""") == 20

    assert sc_eval("""(let ((a (gensym))) (symbol? a))""") == True
    assert sc_eval("""(let ((a 5)) (symbol? a))""") == False


def test_gensym2():
    jlisp_eval, sc_eval = make_interpreter()

    #does gensym work inside of eval and backsplice
    # this was the first time I was able to prove out gensym
    assert sc_eval("""(begin
        (define  b (gensym))
        (eval `(define ,b 20))
    (eval `,b))""") == 20
    assert sc_eval("""(begin
        (define  c (gensym))
        (eval `(define ,c 25))
    `,c)""") == Symbol("GENSYM-1")
    assert sc_eval("""(begin
        (define  d (gensym))
        (eval `(define ,d 20))
    d)""") == Symbol("GENSYM-2")

    assert sc_eval("""(begin
        (define  e (gensym))
        (eval `(define ,e 30))
    (eval 'GENSYM-3))""") == 30


def test_gensym_symbol_value():
    jlisp_eval, sc_eval = make_interpreter()

    #just show how defining a value to a symbol, then referencing that symbol works
    assert sc_eval("""(begin
        (define  a 5)
    a)""") == 5

    #make sure taht symbol-value works on a regularly defined symbol
    assert sc_eval("""(begin
        (define  b 6)
    (symbol-value b))""") == 6


    #Show that we can get a GENSYM from a variable
    assert sc_eval("""(begin
        (define d (gensym))
     (symbol-value d))""") == Symbol("GENSYM-0")


    #make sure we can call symbol-value on a symbol returned from symbol-value
    assert sc_eval("""(begin
        (define  c (gensym))
        (define GENSYM-1 20)
    (symbol-value (symbol-value c)))""") == 20

    # Show a more manual way of setting a value on a gensymed symbol
    assert sc_eval("""(begin
        (define  e (gensym))
        (eval `(define ,e 40))
    (symbol-value (symbol-value e)))""") == 40

    #make sure that the Generated sybol passes expected tests
    generated_symbol = sc_eval("""(gensym)""")
    assert isa(generated_symbol, Symbol)


def test_define_with_symbol_value():
    jlisp_eval, sc_eval = make_interpreter()
    #make sure we can use symbol-value in define
    assert sc_eval("""(begin
        (define a (gensym))
        (define (symbol-value a) 50)
    (symbol-value (symbol-value a)))""") == 50

def test_define_lambda():

    jlisp_eval, sc_eval = make_interpreter()
    # we made a change to define, lets test that it works
    assert sc_eval(
        """(begin
               (define fact (lambda (n) (if (<= n 1) 1 (* n (fact (- n 1))))))
               (fact 3))""") == 6
    assert sc_eval(
        """(begin
               (define fact (lambda (n) (if (<= n 1) 1 (* n (fact (- n 1))))))
               (fact 5))""") == 120

def test_gensym_in_macro():
    jlisp_eval, sc_eval = make_interpreter()
    # show how gensym works in a macro
    res = sc_eval(
        """
        (begin
            (define-macro gs-lambda (lambda args
                (let ((w (gensym)))
                    `(begin
                         (display ',w)
                         (let ((,w 20)) (list ',w ,w))))))
        (gs-lambda))""")
    assert res == [Symbol("GENSYM-0"), 20]
def test_define_macro_separate_invocations():
    jlisp_eval, sc_eval = make_interpreter()
    # show how gensym works in a macro
    res = sc_eval(
        """
        (begin
            (define-macro gs-lambda (lambda args
                (let ((w (gensym)))
                    `(begin
                         (display ',w)
                         (let ((,w 20)) (list ',w ,w))))))
        (gs-lambda))""")
    assert res == [Symbol("GENSYM-0"), 20]
    res = sc_eval(
        """
        (begin
        (gs-lambda))""")
    assert res == [Symbol("GENSYM-1"), 20]
    
