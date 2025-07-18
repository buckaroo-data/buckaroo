from typing_extensions import TypeAlias
from typing import Iterable, List, Type, Union, Any, Mapping, Tuple, Callable, Dict

from buckaroo.df_util import ColIdentifier


SDBaseVals: TypeAlias = Union[str, int, float, bool] #pd.series too, but don't know how
SDVals: TypeAlias = Union[
    SDBaseVals, Iterable[SDBaseVals], Dict[str, SDBaseVals]] 
ColMeta: TypeAlias = Dict[str, SDVals]
#col_name, measure_name, measure_val
#SDType: TypeAlias = Dict[str, ColMeta]
SDType: TypeAlias = Dict[ColIdentifier, ColMeta]



    
class ColAnalysis:
    """
    Col Analysis runs on a single column

    this is the pandas based implementation
    """
    requires_raw = False
    requires_summary:List[str] = [] # What summary stats does this analysis provide

    provides_series_stats:List[str] = [] # what does this provide at a series level
    provides_defaults: ColMeta = {}



    @classmethod
    def full_provides(kls) -> List[str]:
        if not isinstance(kls.provides_defaults, dict):
            raise Exception("no provides Defaults for %r" %kls)
        a = kls.provides_series_stats.copy()
        #I can't figure out why the property won't work here
        a.extend(list(kls.provides_defaults.keys()))
        return a

    @classmethod
    def verify_no_cycle(kls) -> bool:
        requires = set(kls.requires_summary)
        provides = set(kls.provides_defaults.keys())
        if len(requires.intersection(provides)) == 0:
            return True
        return False

    summary_stats_display:Union[List[str], None] = None
    quiet: bool = False
    quiet_warnings:bool = False
    
    @staticmethod
    def series_summary(sampled_ser, ser) -> ColMeta:
        return {}

    @staticmethod
    def computed_summary(summary_dict:ColMeta) -> ColMeta:
        return {}

    @staticmethod
    def column_order(sampled_ser, summary_ser):
        pass

    @staticmethod
    def column_config(summary_dict): # -> ColumnConfig partial without col_name
        pass

    @classmethod
    def cname(kls):
        return kls.__qualname__

    select_clauses:List[Any] = []
    column_ops: Mapping[str, Tuple[List[Any], Callable[[Any], Any]]] = {}


ErrReportType: TypeAlias = Tuple[Exception, Type[ColAnalysis]]
ErrKey: TypeAlias = Tuple[ColIdentifier, str]
ErrDict: TypeAlias = Dict[ErrKey, ErrReportType]

AObjs: TypeAlias = List[Type[ColAnalysis]]


SDErrsTuple: TypeAlias = Tuple[SDType, ErrDict]
