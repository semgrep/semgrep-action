from typing import Any, Dict, Optional, Union
from types import DynamicClassAttribute

T = Any

def glom(
    target: Dict[str, Any], spec: Union[T, str, Dict[str, Any]], default: Any = None
) -> Optional[str]: ...
