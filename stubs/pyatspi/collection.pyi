from pyatspi.atspienum import *
from pyatspi.utils import *
from _typeshed import Incomplete

__all__ = ['Collection', 'SortOrder', 'MatchType', 'TreeTraversalType']

class MatchType(AtspiEnum): ...
class SortOrder(AtspiEnum): ...
class TreeTraversalType(AtspiEnum): ...

class Collection:
    MATCH_ALL: Incomplete
    MATCH_ANY: Incomplete
    MATCH_EMPTY: Incomplete
    MATCH_INVALID: Incomplete
    MATCH_LAST_DEFINED: Incomplete
    MATCH_NONE: Incomplete
    SORT_ORDER_CANONICAL: Incomplete
    SORT_ORDER_FLOW: Incomplete
    SORT_ORDER_INVALID: Incomplete
    SORT_ORDER_LAST_DEFINED: Incomplete
    SORT_ORDER_REVERSE_CANONICAL: Incomplete
    SORT_ORDER_REVERSE_FLOW: Incomplete
    SORT_ORDER_REVERSE_TAB: Incomplete
    SORT_ORDER_TAB: Incomplete
    TREE_INORDER: Incomplete
    TREE_LAST_DEFINED: Incomplete
    TREE_RESTRICT_CHILDREN: Incomplete
    TREE_RESTRICT_SIBLING: Incomplete
    obj: Incomplete
    def __init__(self, obj) -> None: ...
    def isAncestorOf(self, object): ...
    def createMatchRule(self, states, stateMatchType, attributes, attributeMatchType, roles, roleMatchType, interfaces, interfaceMatchType, invert): ...
    def freeMatchRule(self, rule) -> None: ...
    def getMatches(self, rule, sortby, count, traverse): ...
    def getMatchesTo(self, current_object, rule, sortby, tree, recurse, count, traverse): ...
    def getMatchesFrom(self, current_object, rule, sortby, tree, count, traverse): ...
    def getActiveDescendant(self): ...
