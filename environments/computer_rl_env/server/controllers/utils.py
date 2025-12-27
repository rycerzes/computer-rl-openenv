import importlib.util


def is_pyatspi_available() -> bool:
    return importlib.util.find_spec("pyatspi") is not None


def import_pyatspi():
    import pyatspi  # type: ignore

    return pyatspi
