from buckaroo.jlisp.lispy import make_interpreter
from functools import cache
# noqa: E712


#add to read from dictionaries
def dict_get(d, key, default=None):
    return d.get(key, default)
 #pass in a defined function from python

"""

def dict_get(d, key, default=None):
    return d.get(key, default)
 #pass in a defined function from python
jl_eval([s('dict_get'), s('fruits'), 'apple'], {'dict_get': dict_get, 'fruits':{'apple':9}}) == 9 
jl_eval([s('dict_get'), s('fruits'), 'pear', 99], {'dict_get': dict_get, 'fruits':{'apple':9}}) == 99

"""

@cache
def get_rule_interpreter():
    """eval a string as scheme, a list as jlisp"""
    jlisp_eval, sc_eval = make_interpreter()
    sc_eval(MACROS)

    def multi_eval(code, env=None):
        if isinstance(code, list):
            return jlisp_eval(code, env)
        assert isinstance(code, str)
        return sc_eval(code, env)
    return multi_eval




MACROS = """
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


    (define-macro m< (lambda operand
        `(< measure ,@operand)))
    (define primary
        (lambda (other-cond)
            (if other-cond
                (* other-cond 100)
                other-cond)))

    (define-macro f> (lambda operand
        `(if (> measure ,@operand)
             measure #f)))

    ; always return .1
    (define none-rule (lambda _unused .1))
    (define-macro return-measure (lambda operand
        `(if #t
             measure 9)))
)"""

def eval_heuristic_rule(rule, measure):
    _eval = get_rule_interpreter()
    return _eval(rule, {'measure': measure})


def get_top_score(rules, score_dict):
    scores = {}
    for rule_name, rule in rules.items():
        scores[rule_name] = eval_heuristic_rule(rule, score_dict.get(rule_name, 0))
    return max(scores, key=scores.get)
                                                

def eval_heuristics(rules, col_scores):
    chosen_fixes = {}
    for col, scores in col_scores.items():
        chosen_fixes[col] = get_top_score(rules, scores)
    return chosen_fixes
