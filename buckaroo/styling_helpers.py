from buckaroo.dataflow.styling_core import PinnedRowConfig


def obj_(pkey) -> PinnedRowConfig:
    return {'primary_key_val': pkey, 'displayer_args': { 'displayer': 'obj' } }

def float_(pkey, digits=3) -> PinnedRowConfig:
    return {'primary_key_val': pkey,
            'displayer_args': {
                'displayer': 'float', 'min_fraction_digits':digits, 'max_fraction_digits':digits}}

def inherit_(pkey) -> PinnedRowConfig:
    return {'primary_key_val': pkey, 'displayer_args': { 'displayer': 'inherit' } }

def pinned_histogram() -> PinnedRowConfig:
    return {'primary_key_val': 'histogram', 'displayer_args': {'displayer': 'histogram'}}

def pinned_filtered_histogram() -> PinnedRowConfig:
    return {'primary_key_val': '?filtered_histogram', 'displayer_args': {'displayer': 'histogram'}}
