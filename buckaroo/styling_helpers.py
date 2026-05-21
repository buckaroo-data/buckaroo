
def obj_(pkey):
    return {'primary_key_val': pkey, 'displayer_args': { 'displayer': 'obj' } }

def float_(pkey, digits=3):
    return {'primary_key_val': pkey,
            'displayer_args': {
                'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}}

def inherit_(pkey):
    return {'primary_key_val': pkey, 'displayer_args': { 'displayer': 'inherit' } }

def pinned_histogram():
    return {'primary_key_val': 'histogram', 'displayer_args': {'displayer': 'histogram'}}

def pinned_filt_histogram():
    # ``?`` prefix (PR #777): row only renders when ``filtered_histogram``
    # is present in merged_sd — i.e. when a search filter is active and
    # the filt scope's SD has been layered in (PR #785).
    return {'primary_key_val': '?filtered_histogram', 'displayer_args': {'displayer': 'histogram'}}
