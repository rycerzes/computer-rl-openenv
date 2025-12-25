from abc import ABC, abstractmethod


class VMProvider(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def execute(self, cmd: str) -> str:
        pass

    @abstractmethod
    def get_display(self) -> str:
        pass
