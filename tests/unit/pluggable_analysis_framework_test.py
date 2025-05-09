import pandas as pd
import unittest
import graphlib
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (
    ColAnalysis, order_analysis, check_solvable, NotProvidedException, SelfCycle)
from buckaroo.pluggable_analysis_framework.utils import cache_series_func, hash_series


from .fixtures import (DistinctCount, Len, DistinctPer, DCLen, DependsNoProvides)

class NoRoute(ColAnalysis):    
    provides_defaults = {'not_used': False}
    requires_summary = ["does_not_exist"]

class SelfCycleA(ColAnalysis):
    provides_defaults = {'cycle_a': 'asdf'}

    requires_summary = ["cycle_a"]

    
class CycleA(ColAnalysis):
    provides_defaults = {'cycle_a': 'asdf', 'extra_from_class_a':'asdf'}
    #provides_defaults = {'cycle_a': 'asdf'}
    requires_summary = ["cycle_b"]

class CycleB(ColAnalysis):
    provides_defaults = {'cycle_b': 'foo'}
    requires_summary = ["cycle_a"]




class CA_AB(ColAnalysis):
    provides_summary = {"a":0, "b":99}

class CA_CD(ColAnalysis):
    provides_summary = {"c":3, "d":1}

class CA_EF(ColAnalysis):
    provides_defaults = {"e":9, "f":2}
    requires_summary = ["a", "b", "c", "d"]

class CA_G(ColAnalysis):
    provides_defaults = {"g":3}
    requires_summary = ["e"]


class TestOrderAnalysis(unittest.TestCase):

    def test_default_order(self):
        self.assertEqual(
            order_analysis([DistinctCount, Len, DistinctPer]),
            [DistinctCount, Len, DistinctPer])
        self.assertEqual(
            order_analysis([DistinctPer, DistinctCount, Len]),
            [DistinctCount, Len, DistinctPer])
    
    def test_multiple_provides(self):
        self.assertEqual(
            order_analysis([DCLen, DistinctPer]),
            [DCLen, DistinctPer])
        self.assertEqual(
            order_analysis([DistinctPer, DCLen]),
            [DCLen, DistinctPer])
        self.assertEqual(
            order_analysis([CA_G, CA_CD, CA_AB, CA_EF]),
            [CA_CD, CA_AB, CA_EF, CA_G ])
            #note the order between CA_CD and CA_AB doesn't matter - 
            # as long as they occur before other classes

    def test_no_provides(self):
        # order_analysis should work properly with ColAnalysis objects that don't provide any summary_stats

        self.assertEqual(
            order_analysis([DCLen, DistinctPer, DependsNoProvides]),
            [DCLen, DependsNoProvides, DistinctPer])

    def test_cycle(self):
        with self.assertRaises(graphlib.CycleError):
            order_analysis([CycleA, CycleB])

    def test_self_cycle(self):
        with self.assertRaises(SelfCycle):
            check_solvable([SelfCycleA])
            
    def test_no_route(self):
        check_solvable([Len])
        with self.assertRaises(NotProvidedException):
            check_solvable([NoRoute])


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
