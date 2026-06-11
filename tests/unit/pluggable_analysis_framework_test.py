import pandas as pd
import unittest
from buckaroo.df_util import to_chars
from buckaroo.pluggable_analysis_framework.utils import cache_series_func, hash_series


class TestCacheSeriesFunc(unittest.TestCase):
    def test_hash_series_unique(self):
        ser_a = pd.Series([1,2,3,4])
        ser_b = pd.Series([4,2,3,1])
        ser_c = pd.Series([10.0,2.0,3.0,4.0])
        ser_d = pd.Series([4.0,3.0,2.0,10.0])

        ser_e = pd.Series([True, False])
        ser_f = pd.Series([False, True])

        ser_g = pd.Series(["foo", "bar", "baz"])
        ser_h = pd.Series(["baz", "foo", "bar"])



        all_series = [
            ser_a, ser_b, ser_c, ser_d,
            ser_e, ser_f, ser_g, ser_h]

        #make sure each of the 8 series hashes differently
        assert len(set(map(hash_series, all_series))) == 8

    def test_hash_series_repeatable(self):
        ser_a = pd.Series([1,2,3,4])
        ser_b = pd.Series([1,2,3,4])

        assert hash_series(ser_a) == hash_series(ser_b)

    def test_memoize_works(self):


        def myfunction(ser):
            myfunction.counter += 1
            assert isinstance(ser, pd.Series)
            return ser.sum()
        myfunction.counter = 0

        ser_a = pd.Series([1,2,3,4])
        ser_b = pd.Series([4,2,3,1])
        ser_c = pd.Series([10.0,2.0,3.0,4.0])
        ser_d = pd.Series([4.5,3.0,2.0,10.0])

        assert myfunction(ser_a) == 10
        assert myfunction.counter == 1
        assert myfunction(ser_b) == 10
        assert myfunction.counter == 2

        assert myfunction(ser_a) == 10
        assert myfunction.counter == 3

        @cache_series_func
        def myfunction2(ser):
            myfunction2.counter += 1
            print("145", type(ser))
            assert isinstance(ser, pd.Series)
            return ser.sum()
        myfunction2.counter = 0

        assert myfunction2(ser_a) == 10
        assert myfunction2.counter == 1
        assert myfunction2(ser_b) == 10
        assert myfunction2.counter == 2

        assert myfunction2(ser_a) == 10
        #it isn't called again
        assert myfunction2.counter == 2

        assert myfunction2(ser_c) == 19
        assert myfunction2.counter == 3
        assert myfunction2(ser_c) == 19
        assert myfunction2.counter == 3

        assert myfunction2(ser_d) == 19.5
        assert myfunction2.counter == 4



    def test_memoize_gc(self):
        # we set the series to None after it's used, make sure that everything works when the maxsize si reached

        max_size = 256
        all_sers = []
        for i in range(max_size+1):
            all_sers.append(pd.Series([i, i+1]))

        @cache_series_func
        def myfunction3(ser):
            myfunction3.counter += 1
            assert isinstance(ser, pd.Series)
            return ser.sum()
        myfunction3.counter = 0
        myfunction3(pd.Series([3]))
        assert myfunction3.counter == 1
        [myfunction3(ser) for ser in all_sers[:(max_size - 2)]]
        assert myfunction3.counter == 255
        [myfunction3(ser) for ser in all_sers[:(max_size - 2)]]
        assert myfunction3.counter == 255
        [myfunction3(ser) for ser in all_sers]
        assert myfunction3.counter == 258 # we had to re-execute some functions


    def test_to_chars(self):
        assert to_chars(0) == 'a'
        assert to_chars(1) == 'b'
        assert to_chars(25) == 'z'
        assert to_chars(26) == 'ba'  #should be aa
        assert to_chars(27) == 'bb'
