import json

def assert_dict_eq(expected, actual):
    expected_keys = sorted(expected.keys())
    actual_keys = sorted(actual.keys())
    assert expected_keys == actual_keys
    for k in actual_keys:
        if not json.dumps(actual[k]) == json.dumps(expected[k]):
            print("FAIL" + "%" * 50)
            print(k)
            print(expected[k])
            print(actual[k])
            assert expected[k] == actual[k]
#            assert (k, expected[k]) == (k, actual[k])
