from typing import Any, Dict, Optional, Union
from types import DynamicClassAttribute

class TType:
    def __getattr__(self, attr: str) -> "TType": ...
    def __getitem__(self, item: Union[int, str]) -> "TType": ...

T: TType

def glom(
    target: Dict[str, Any], spec: Union[TType, str, Dict[str, Any]], default: Any = None
) -> Optional[str]: ...
