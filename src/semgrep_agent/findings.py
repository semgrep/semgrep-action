import binascii
import textwrap
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any
from typing import Collection
from typing import Dict
from typing import Iterable
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
    index = attr.ib(type=int, default=0)
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
        str_id = str((self.check_id, self.path, self.syntactic_context, self.index))
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
        cls, result: Dict[str, Any], committed_datetime: Optional[datetime],
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
            commit_date=committed_datetime,
            metadata=result["extra"]["metadata"],
        )

    def to_dict(self, omit: Set[str]) -> Mapping[str, Any]:
        d = attr.asdict(self)
        d = {k: v for k, v in d.items() if v is not None and k not in omit}
        d["syntactic_id"] = self.syntactic_identifier_str()
        d["commit_date"] = d["commit_date"].isoformat()
        return d


class FindingSet(Set[Finding]):
    """
    A set type which is aware
    that two findings are not to be considered the same
    even if they have the same line of code.

    It amends findings that have identical code during insertion
    to set a unique zero-indexed "index" value on them.
    """

    def add_finding(self, finding: Finding) -> None:
        """
        Add finding, even if the same (rule, path, code) existed.

        This is used over regular `.add` to increment the finding's index
        if it already exists in the set, thereby retaining multiple copies
        of the same (rule_id, path, line_of_code) tuple.
        """
        while finding in self:
            finding = attr.evolve(finding, index=finding.index + 1)
        self.add(finding)

    def update_findings(self, findings: Iterable[Finding]) -> None:
        """
        Add findings, even if the same (rule, path, code) exist.

        This is used over regular `.update` to increment the findings' indexes
        if they already exists in the set, thereby retaining multiple copies
        of the same (path, rule_id, line_of_code) tuples.
        """
        for finding in findings:
            self.add_finding(finding)


@dataclass(frozen=True)
class FindingSets:
    baseline: FindingSet = field(default_factory=FindingSet)
    current: FindingSet = field(default_factory=FindingSet)

    @property
    def new(self) -> Set[Finding]:
        return self.current - self.baseline
