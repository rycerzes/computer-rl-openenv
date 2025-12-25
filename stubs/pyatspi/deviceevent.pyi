from pyatspi.atspienum import *
from _typeshed import Incomplete
from collections.abc import Generator

class PressedEventType(AtspiEnum): ...

KEY_PRESSED_EVENT: Incomplete
KEY_RELEASED_EVENT: Incomplete
BUTTON_PRESSED_EVENT: Incomplete
BUTTON_RELEASED_EVENT: Incomplete

class ControllerEventMask(AtspiEnum): ...

KEY_PRESSED_EVENT_MASK: Incomplete
KEY_RELEASED_EVENT_MASK: Incomplete
BUTTON_PRESSED_EVENT_MASK: Incomplete
BUTTON_RELEASED_EVENT_MASK: Incomplete

class KeyEventType(AtspiEnum): ...

KEY_PRESSED: Incomplete
KEY_RELEASED: Incomplete

class KeySynthType(AtspiEnum): ...

KEY_LOCKMODIFIERS: Incomplete
KEY_PRESS: Incomplete
KEY_PRESSRELEASE: Incomplete
KEY_RELEASE: Incomplete
KEY_STRING: Incomplete
KEY_SYM: Incomplete
KEY_UNLOCKMODIFIERS: Incomplete

class ModifierType(AtspiEnum): ...

MODIFIER_ALT: Incomplete
MODIFIER_CONTROL: Incomplete
MODIFIER_META: Incomplete
MODIFIER_META2: Incomplete
MODIFIER_META3: Incomplete
MODIFIER_NUMLOCK: Incomplete
MODIFIER_SHIFT: Incomplete
MODIFIER_SHIFTLOCK: Incomplete

def allModifiers() -> Generator[Incomplete]: ...

class DeviceEvent(list):
    def __new__(cls, type, id, hw_code, modifiers, timestamp, event_string, is_text): ...
    consume: bool
    def __init__(self, type, id, hw_code, modifiers, timestamp, event_string, is_text) -> None: ...
    type: Incomplete
    id: Incomplete
    hw_code: Incomplete
    modifiers: Incomplete
    timestamp: Incomplete
    event_string: Incomplete
    is_text: Incomplete

class EventListenerMode(list):
    def __new__(cls, synchronous, preemptive, global_): ...
    def __init__(self, synchronous, preemptive, global_) -> None: ...
    synchronous: Incomplete
    preemptive: Incomplete
    global_: Incomplete

class KeyDefinition(list):
    def __new__(cls, keycode, keysym, keystring, unused): ...
    def __init__(self, keycode, keysym, keystring, unused) -> None: ...
    keycode: Incomplete
    keysym: Incomplete
    keystring: Incomplete
    unused: Incomplete
