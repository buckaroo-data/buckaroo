
def obj_(pkey):
    return {'primary_key_val': pkey, 'displayer_args': { 'displayer': 'obj' } }

def float_(pkey, digits=3):
    return {'primary_key_val': pkey, 
            'displayer_args': {
                'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}}
def pinned_histogram():
    return {'primary_key_val': 'histogram', 'displayer_args': {'displayer': 'histogram'}}
