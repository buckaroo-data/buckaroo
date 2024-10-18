"""
It would be awesome to have cleaning and verification commands that add new columns with related names

The new columns are null accept for errored values.

Could use this to show original values that were removed/cleaned.  Combined with conditional styling in the UI

sick.  And still ahve high perfromance properly typed columns



"""

def is_symbol(obj):
    return isinstance(obj, dict) and "symbol" in obj

def is_generated_symbol(obj):
    return is_symbol(obj) and obj.get("meta", False)

def split_operations(full_operations):
    """
    utitlity to split a combined set of operations with machine generated commands and user entered commands into two lists, machine_generated and user_generated

    machine_generated commands have function calls with the symbol token also having a meta key with a value of {"precleaning":True}
    """

    machine_generated, user_entered = [], []
    for command in full_operations:
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

def lists_match(l1, l2):
    #https://note.nkmk.me/en/python-list-compare/#checking-the-exact-match-of-lists
    if len(l1) != len(l2):
        return False
    return all(x == y and type(x) is type(y) for x, y in zip(l1, l2))

            
def qc_sym(symbol_name):
    return {'symbol':symbol_name, 'meta':{'auto_clean': True, 'quick_command':True}}

def s(symbol_name):
    return {'symbol':symbol_name}
    
