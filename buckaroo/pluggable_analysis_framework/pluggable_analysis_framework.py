import graphlib
from collections import OrderedDict
from typing import List, Union

class ColAnalysis(object):
    """
    Col Analysis runs on a single column

    this is the pandas based implementation
    """
    requires_raw = False
    requires_summary:List[str] = [] # What summary stats does this analysis provide
    provides_summary:List[str] = [] # mean/max/histogram

    provides_series_stats:List[str] = [] # what does this provide at a series level


    @classmethod
    def full_provides(cls):
        a = cls.provides_series_stats.copy()
        a.extend(cls.provides_summary)
        return a

    summary_stats_display:Union[List[str], None] = None
    quiet = False
    quiet_warnings = False
    
    @staticmethod
    def series_summary(sampled_ser, ser):
        return {}

    @staticmethod
    def computed_summary(summary_dict):
        return {}

    @staticmethod
    def column_order(sampled_ser, summary_ser):
        pass

    @classmethod
    def cname(kls):
        #print(dir(kls))
        return kls.__qualname__
    
class NotProvidedException(Exception):
    pass

def check_solvable(a_objs):
    """
    checks that all of the required  inputs are provided by another analysis object.
    """
    provides = []
    required = []
    for ao in a_objs:
        rest = ao.full_provides()
        provides.extend(rest)

        required.extend(ao.requires_summary)
    all_provides = set(provides)
    all_required = set(required)
    if not all_required.issubset(all_provides):
        missing = all_required - all_provides
        raise NotProvidedException("Missing provided analysis for %r" % missing)

def remove_duplicates(lst):
    return list(OrderedDict.fromkeys(lst))

def clean_list(full_class_list):
    only_kls_lst = [kls for kls in full_class_list if kls is not None]
    #note I also want someway to detect that classes don't alternate
    # ['a', 'a', 'b', 'c', 'c'] # fine
    # ['a', 'a', 'b', 'a', 'c'] # something went wrong with the graph algo
    return remove_duplicates(only_kls_lst)


def order_analysis(a_objs):
    """order a set of col analysis objects such that the dag of their
    provides_summary and requires_summary is ordered for computation
    """

    graph = {}
    key_class_objs = {}
    for ao in a_objs:
        fp = ao.full_provides()
        if len(fp) == 0:
            temp_provided = "__no_provided_keys__"
        else:
            temp_provided = fp[0]
        first_mid_key = mid_key = ao.__name__ + "###" + temp_provided
        for k in ao.full_provides()[1:]:
            #print("k", k)
            next_mid_key = ao.__name__ + "###" + k
            graph[mid_key] = set([next_mid_key])
            key_class_objs[mid_key] = ao
            mid_key = next_mid_key
        graph[mid_key] = set(ao.requires_summary)
        key_class_objs[mid_key] = ao
        for j in ao.full_provides():
            #print("j", j)
            graph[j] = set([first_mid_key])
    ts = graphlib.TopologicalSorter(graph)
    seq =  tuple(ts.static_order())
    #print("seq", seq)
    full_class_list = [key_class_objs.get(k, None) for k in seq]
    return clean_list(full_class_list)
