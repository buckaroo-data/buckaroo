import json
"""
It would be awesome to have cleaning and verification commands that add new columns with related names

The new columns are null accept for errored values.

Could use this to show original values that were removed/cleaned.  Combined with conditional styling in the UI

sick.  And still ahve high perfromance properly typed columns



"""

def is_symbol(obj):
    return isinstance(obj, dict) and "symbol" in obj

def is_generated_symbol(obj):
    return is_symbol(obj) and obj.get("meta", False) and obj['meta'].get('auto_clean', False)

def split_operations(full_operations):
    """
    utitlity to split a combined set of operations with machine generated commands and user entered commands into two lists, machine_generated and user_generated

    machine_generated commands have function calls with the symbol token also having a meta key with a value of {"precleaning":True}
    """

    machine_generated, user_entered = [], []
    for command in full_operations:
        if not isinstance(command, list):
            print("command should be a list", command)
        assert isinstance(command, list)
        sym_atom = command[0]
        if is_symbol(sym_atom):
            if is_generated_symbol(sym_atom):
                machine_generated.append(command)
            else:
                user_entered.append(command)
            continue
        raise Exception("Unexpected token %r" % command)
    return machine_generated, user_entered


def sym_meta_get(sym, meta_key:str) -> str:
    assert is_symbol(sym)
    meta = sym.get('meta', {})
    return meta.get(meta_key, None)
    

def op_meta_get(operation, meta_key:str)-> str: #takes a full Operation
    return sym_meta_get(operation[0], meta_key)

def merge_ops(existing_ops, cleaning_ops):
    """strip cleaning_ops from existing_ops, reinsert cleaning_ops at
    the beginning, leave the non auto_clean True ops"""
    old_cleaning_ops, user_gen_ops = split_operations(existing_ops)
    clean_cols = set([op_meta_get(op, 'clean_col') for op in user_gen_ops]) - {None}
    merged = cleaning_ops.copy()
    stripped_merged = [op for op in merged if op_meta_get(op, 'clean_col') not in clean_cols]
    stripped_merged.extend(user_gen_ops)  # we want the user cleaning ops to come last
    return stripped_merged



def format_ops(column_meta):
    """
    translate summary_dict with cleaning_ops to real, usable instructions
    """
    ret_ops = []
    for k,v in column_meta.items():
        if k == 'index':
            continue
        if 'cleaning_ops' not in v:
            continue
        ops = v['cleaning_ops']
        if len(ops) > 0:
            temp_ops = ops.copy()
            temp_ops.insert(2, k)
            ret_ops.append(temp_ops)
    return ret_ops

def ops_eq(ops_a, ops_b):
    return json.dumps(ops_a) == json.dumps(ops_b)


def lists_match(l1, l2):
    #https://note.nkmk.me/en/python-list-compare/#checking-the-exact-match-of-lists
    if len(l1) != len(l2):
        return False
    return all(x == y and type(x) is type(y) for x, y in zip(l1, l2))


def s(symbol_name:str, **extra_meta_kwargs):
    "return a symbol with auto_clean:True"
    meta = extra_meta_kwargs.copy()
    if meta:
        return {'symbol': symbol_name, 'meta': meta}
    return {'symbol': symbol_name}
    
    

def sA(symbol_name:str, **extra_meta_kwargs):
    "return a symbol with auto_clean:True"
    meta = extra_meta_kwargs.copy()
    meta['auto_clean'] = True
    return {'symbol': symbol_name, 'meta': meta}

def sQ(symbol_name, **extra_meta_kwargs):
    """ auto_clean:True because we want this cleared when switching cleaning
    """
    meta = extra_meta_kwargs.copy()
    meta['auto_clean'] = True
    meta['quick_command'] = True
    return {'symbol': symbol_name, 'meta': meta}

