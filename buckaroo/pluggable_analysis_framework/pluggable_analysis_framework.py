import graphlib
from collections import OrderedDict
from .col_analysis import AObjs

    
class NotProvidedException(Exception):
    pass

def check_solvable(a_objs:AObjs) -> None:
    """
    checks that all of the required  inputs are provided by another analysis object.
    """
    provides = []
    required = []
    for ao in a_objs:
        if ao.verify_no_cycle() is False:
            raise SelfCycle(f"{ao} depends on itself")
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



class SelfCycle(Exception):
    pass

def order_analysis(a_objs:AObjs) -> AObjs:
    """order a set of col analysis objects such that the dag of their
    provides_summary and requires_summary is ordered for computation
    """

    graph = {}
    key_class_objs = {} #from class+prop name to class object

    # graph is an object with keys of 'prop' or class and values of the prop or class it depends on
    # classnames are of the form "ClassName###first_provided_prop

    # these fixes aren't complete.  look at https://github.com/paddymul/buckaroo/issues/352
    # for some more explanation
    
    for ao in a_objs:
        fp = ao.full_provides()
        if len(fp) == 0:
            temp_provided = "__no_provided_keys__"
        else:
            temp_provided = fp[0]
        first_mid_key = mid_key = ao.__name__ + "###" + temp_provided
        for k in ao.full_provides()[1:]:
            next_mid_key = ao.__name__ + "###" + k
            graph[mid_key] = set([next_mid_key])
            key_class_objs[mid_key] = ao
            mid_key = next_mid_key
        graph[mid_key] = set(ao.requires_summary)
        key_class_objs[mid_key] = ao
        for j in ao.full_provides():
            graph[j] = set([first_mid_key])
    ts = graphlib.TopologicalSorter(graph)
    try:
        seq = tuple(ts.static_order())
    except graphlib.CycleError as e:
        print("e", e)
        print("graph", graph)
        raise
    full_class_list = [key_class_objs.get(k, None) for k in seq]
    return clean_list(full_class_list)
