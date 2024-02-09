import pandas as pd
from buckaroo.serialization_utils import df_to_obj

def test_df_to_obj():
    named_index_df = pd.DataFrame(
        dict(names=['one', 'two', 'three'],
             values=[1, 2, 3])).set_index('names')

    serialized_df = df_to_obj(named_index_df, {})
    assert serialized_df['data'][0]['names'] == 'one'

# def test_int_overflow_validation():
#     value=float('nan')
#     class Model(BaseModel):
#         a: int
#     Model(a=3)
#     with pytest.raises(ValidationError) as exc_info:
#         Model(a=value)
#     assert exc_info.value.errors(include_url=False) == [
#         {'type': 'finite_number', 'loc': ('a',), 'msg': 'Input should be a finite number',
#          'input': value
#          }]
