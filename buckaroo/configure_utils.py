from .lispy import make_interpreter
def configure_buckaroo(transforms):
    command_defaults = {}
    command_patterns = {}

    transform_lisp_primitives = {}
    to_py_lisp_primitives = {}
    for T in transforms:
        t = T()
        transform_name = t.command_default[0]['symbol']
        command_defaults[transform_name] = t.command_default
        command_patterns[transform_name] = t.command_pattern
        transform_lisp_primitives[transform_name] = T.transform
        to_py_lisp_primitives[transform_name] = T.transform_to_py
    
    buckaroo_eval, raw_parse = make_interpreter(transform_lisp_primitives)
    def buckaroo_transform(instructions, df):
        df_copy = df.copy()
        ret_val =  buckaroo_eval(instructions, {'df':df_copy})
        #print(ret_val)
        return ret_val

    convert_to_python, __unused = make_interpreter(to_py_lisp_primitives)
    def buckaroo_to_py(instructions):
        #I would prefer to implement this with a macro named something
        #like 'clean' that is implemented for the _convert_to_python
        #interpreter to return a string code block, and for the real DCF
        #interpreter as 'begin'... that way the exact same instructions
        #could be sent to either interpreter.  For now, this will do
        individual_instructions =  [x for x in map(lambda x:convert_to_python(x, {'df':5}), instructions)]
        #print("individual_instructions", individual_instructions)
        code_block =  '\n'.join(individual_instructions)

        return "def clean(df):\n" + code_block + "\n    return df"
    return command_defaults, command_patterns, buckaroo_transform, buckaroo_to_py
