from typing import Any, Iterable, TypeVar

Item = TypeVar("Item")
Items = Iterable[Item]

def chunked_iter(src: Items, size: int, **kw: Any) -> Iterable[Items]: ...
