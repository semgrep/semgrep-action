import binascii
import hashlib
import textwrap
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any
from typing import Dict
from typing import Mapping
from typing import NamedTuple
from typing import Optional
from typing import Set

import attr
import click
import pymmh3


@attr.s(frozen=True, hash=False)
class Finding:
    """
    N.B.: line and column are 1-based, not 0-based
    """

    check_id = attr.ib(type=str)
    path = attr.ib(type=str)
    line = attr.ib(type=int, hash=None, eq=False)
    column = attr.ib(type=int, hash=None, eq=False)
    message = attr.ib(type=str, hash=None, eq=False)
    severity = attr.ib(type=int, hash=None, eq=False)
    syntactic_context = attr.ib(type=str, converter=textwrap.dedent)
    end_line = attr.ib(
        type=Optional[int], default=None, hash=None, eq=False, kw_only=True
    )
    end_column = attr.ib(
        type=Optional[int], default=None, hash=None, eq=False, kw_only=True
    )
    commit_date = attr.ib(
        type=Optional[datetime], default=None, hash=None, eq=False, kw_only=True
    )
    metadata = attr.ib(type=Mapping[str, Any], hash=None, eq=False, kw_only=True)

    def is_blocking(self) -> bool:
        """
            Returns if this finding indicates it should block CI
        """
        return "block" in self.metadata.get("dev.semgrep.actions", ["block"])

    def syntactic_identifier_int(self) -> int:
        # Use murmur3 hash to minimize collisions
        str_id = str((self.check_id, self.path, self.syntactic_context))
        return pymmh3.hash128(str_id)

    def syntactic_identifier_str(self) -> str:
        id_bytes = int.to_bytes(
            self.syntactic_identifier_int(), byteorder="big", length=16, signed=False
        )
        return str(binascii.hexlify(id_bytes), "ascii")

    def __hash__(self) -> int:
        # attr.s equality uses all elements of syntactic_identifier, so
        # hash->equality contract is guaranteed
        return self.syntactic_identifier_int()

    @staticmethod
    def semgrep_severity_to_int(severity: str) -> int:
        if severity == "ERROR":
            return 2
        elif severity == "WARNING":
            return 1
        else:
            return 0

    @classmethod
    def from_semgrep_result(
        cls, result: Dict[str, Any], ctx: click.Context
    ) -> "Finding":
        return cls(
            check_id=result["check_id"],
            path=result["path"],
            line=result["start"]["line"],
            column=result["start"]["col"],
            end_line=result["end"]["col"],
            end_column=result["end"]["col"],
            message=result["extra"]["message"],
            severity=cls.semgrep_severity_to_int(result["extra"]["severity"]),
            syntactic_context=result["extra"]["lines"],
            commit_date=ctx.obj.meta.commit.committed_datetime
            if ctx.obj.meta.commit
            else None,
            metadata=result["extra"]["metadata"],
        )

    def to_dict(self) -> Mapping[str, Any]:
        d = attr.asdict(self)
        d = {k: v for k, v in d.items() if v is not None}
        d["syntactic_id"] = self.syntactic_identifier_str()
        d["commit_date"] = d["commit_date"].isoformat()
        return d


@dataclass(frozen=True)
class FindingSets:
    baseline: Set[Finding] = field(default_factory=set)
    current: Set[Finding] = field(default_factory=set)

    @property
    def new(self) -> Set[Finding]:
        return self.current - self.baseline
