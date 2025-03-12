import unittest
import graphlib
from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (
    ColAnalysis, order_analysis, check_solvable, NotProvidedException, SelfCycle)



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
