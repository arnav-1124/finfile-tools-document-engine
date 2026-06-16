from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseParser(ABC):
    parser_mode = "base"

    @abstractmethod
    def parse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
