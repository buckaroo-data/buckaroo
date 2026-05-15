import pandas as pd
from .lispy import make_interpreter
def configure_buckaroo(transforms):
    command_defaults = {}
    command_patterns = {}

    # Accumulates sd_updates from transforms that return (df, sd_updates).
    # Reset on each buckaroo_transform call; readable afterwards via
    # buckaroo_transform.get_last_sd_updates().
    sd_accumulator = {}

    def _wrap_transform(orig):
        def wrapped(*args, **kwargs):
            result = orig(*args, **kwargs)
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
                df, sd_updates = result
                for col, kv in sd_updates.items():
                    sd_accumulator.setdefault(col, {}).update(kv)
                return df
            return result
        return wrapped

    transform_lisp_primitives = {}
    to_py_lisp_primitives = {}
    for T in transforms:
        t = T()
        transform_name = t.command_default[0]['symbol']
        command_defaults[transform_name] = t.command_default
        command_patterns[transform_name] = t.command_pattern
        transform_lisp_primitives[transform_name] = _wrap_transform(T.transform)
        to_py_lisp_primitives[transform_name] = T.transform_to_py

    buckaroo_eval, raw_parse = make_interpreter(transform_lisp_primitives)

    def buckaroo_transform(instructions, df):
        sd_accumulator.clear()
        if isinstance(df, pd.DataFrame):
            df_copy = df.copy()
        else: # hack we know it's polars here... just getting something working for now
            df_copy = df.clone()
        ret_val =  buckaroo_eval(instructions, {'df':df_copy})
        return ret_val

    def get_last_sd_updates():
        # Snapshot — callers should not mutate the live accumulator.
        return {col: dict(kv) for col, kv in sd_accumulator.items()}

    buckaroo_transform.get_last_sd_updates = get_last_sd_updates

    convert_to_python, __unused = make_interpreter(to_py_lisp_primitives)
    def buckaroo_to_py(instructions):
        #I would prefer to implement this with a macro named something
        #like 'clean' that is implemented for the _convert_to_python
        #interpreter to return a string code block, and for the real DCF
        #interpreter as 'begin'... that way the exact same instructions
        #could be sent to either interpreter.  For now, this will do
        individual_instructions =  [x for x in map(lambda x:convert_to_python(x, {'df':5}), instructions)]
        code_block =  '\n'.join(individual_instructions)
        return "def clean(df):\n" + code_block + "\n    return df"
    return command_defaults, command_patterns, buckaroo_transform, buckaroo_to_py
