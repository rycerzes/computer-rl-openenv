from pyatspi.atspienum import *
from pyatspi.utils import *
from pyatspi.interface import *
from _typeshed import Incomplete

__all__ = ['CoordType', 'XY_SCREEN', 'XY_WINDOW', 'XY_PARENT', 'ComponentLayer', 'Component', 'LAYER_BACKGROUND', 'LAYER_CANVAS', 'LAYER_INVALID', 'LAYER_LAST_DEFINED', 'LAYER_MDI', 'LAYER_OVERLAY', 'LAYER_POPUP', 'LAYER_WIDGET', 'LAYER_WINDOW', 'ScrollType', 'SCROLL_TOP_LEFT', 'SCROLL_BOTTOM_RIGHT', 'SCROLL_TOP_EDGE', 'SCROLL_BOTTOM_EDGE', 'SCROLL_LEFT_EDGE', 'SCROLL_RIGHT_EDGE', 'SCROLL_ANYWHERE']

class CoordType(AtspiEnum): ...

XY_SCREEN: Incomplete
XY_WINDOW: Incomplete
XY_PARENT: Incomplete

class ComponentLayer(AtspiEnum): ...

LAYER_BACKGROUND: Incomplete
LAYER_CANVAS: Incomplete
LAYER_INVALID: Incomplete
LAYER_LAST_DEFINED: Incomplete
LAYER_MDI: Incomplete
LAYER_OVERLAY: Incomplete
LAYER_POPUP: Incomplete
LAYER_WIDGET: Incomplete
LAYER_WINDOW: Incomplete

class ScrollType(AtspiEnum): ...

SCROLL_ANYWHERE: Incomplete
SCROLL_BOTTOM_EDGE: Incomplete
SCROLL_BOTTOM_RIGHT: Incomplete
SCROLL_LEFT_EDGE: Incomplete
SCROLL_RIGHT_EDGE: Incomplete
SCROLL_TOP_EDGE: Incomplete
SCROLL_TOP_LEFT: Incomplete

class Component(interface):
    def contains(self, x, y, coord_type): ...
    def getAccessibleAtPoint(self, x, y, coord_type): ...
    def getAlpha(self): ...
    def getExtents(self, coord_type): ...
    def getLayer(self): ...
    def getMDIZOrder(self): ...
    def getPosition(self, coord_type): ...
    def getSize(self): ...
    def grabFocus(self): ...
    def scrollTo(self, scroll_type): ...
    def scrollToPoint(self, coord_type, x, y): ...
