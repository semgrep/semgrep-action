import binascii
import hashlib
import textwrap
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any
from typing import Dict
from typing import List
from typing import Mapping
from typing import Optional
from typing import Set
from typing import Tuple

import attr
import pymmh3


@attr.s(frozen=True)
class FindingKey:
    check_id = attr.ib(type=str)
    path = attr.ib(type=str)
    syntactic_context = attr.ib(type=str)


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
    index = attr.ib(type=int, hash=None, eq=False)
    syntactic_context = attr.ib(type=str, converter=textwrap.dedent)
    metadata = attr.ib(type=Mapping[str, Any], hash=None, eq=False, kw_only=True)
    end_line = attr.ib(
        type=Optional[int], default=None, hash=None, eq=False, kw_only=True
    )
    end_column = attr.ib(
        type=Optional[int], default=None, hash=None, eq=False, kw_only=True
    )
    commit_date = attr.ib(
        type=Optional[datetime], default=None, hash=None, eq=False, kw_only=True
    )

    def is_blocking(self) -> bool:
        """
            Returns if this finding indicates it should block CI
        """
        return "block" in self.metadata.get("dev.semgrep.actions", ["block"])

    def syntactic_identifier_int(self) -> int:
        # Use murmur3 hash to minimize collisions
        str_id = str((self.check_id, self.path, self.index, self.syntactic_context))
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
        cls, result: Dict[str, Any], committed_datetime: Optional[datetime]
    ) -> Tuple[FindingKey, "Finding"]:
        check_id = result["check_id"]
        path = result["path"]
        syntactic_context = result["extra"]["lines"]

        key = FindingKey(
            check_id=check_id, path=path, syntactic_context=syntactic_context,
        )
        finding = cls(
            check_id=check_id,
            path=path,
            index=0,
            line=result["start"]["line"],
            column=result["start"]["col"],
            end_line=result["end"]["col"],
            end_column=result["end"]["col"],
            message=result["extra"]["message"],
            severity=cls.semgrep_severity_to_int(result["extra"]["severity"]),
            syntactic_context=syntactic_context,
            commit_date=committed_datetime,
            metadata=result["extra"]["metadata"],
        )
        return key, finding

    def to_dict(self) -> Mapping[str, Any]:
        d = attr.asdict(self)
        d = {k: v for k, v in d.items() if v is not None}
        d["syntactic_id"] = self.syntactic_identifier_str()
        d["commit_date"] = d["commit_date"].isoformat()
        return d


@dataclass(frozen=True)
class FindingSets:
    """
    Accumulates findings to calculate which findings are new from this commit

    Usage:
    Add current and baseline findings using update_current and update_baseline.
    New findings will calculate findings in current that don't show up in the baseline.

    Findings have distinct hashes based on (rule id, path, syntactic context, index in file)
    """

    # When accumulating findings, we don't yet know indices of findings, so we
    # keep track of a list of findings per (rule id, path, syntactic context) tuple.
    # We then later get the findings with proper indices when calculating new findings
    # in FindingSets.expensive_new().
    _baseline_map: Dict[FindingKey, List[Finding]] = field(default_factory=dict)
    _current_map: Dict[FindingKey, List[Finding]] = field(default_factory=dict)

    def expensive_new(self) -> Set[Finding]:
        return self._map_to_set(self._current_map) - self._map_to_set(
            self._baseline_map
        )

    @staticmethod
    def _map_to_set(mapping: Mapping[FindingKey, List[Finding]]) -> Set[Finding]:
        return set(
            attr.evolve(finding, index=index)
            for findings_for_key in mapping.values()
            for index, finding in enumerate(findings_for_key)
        )

    @staticmethod
    def _update_findings_map(
        result: Dict[str, Any],
        committed_datetime: Optional[datetime],
        findings_map: Dict[FindingKey, List[Finding]],
    ) -> None:
        key, finding = Finding.from_semgrep_result(result, committed_datetime)
        for_key = findings_map.get(key, [])
        for_key.append(finding)
        findings_map[key] = for_key

    def update_baseline(
        self, result: Dict[str, Any], committed_datetime: Optional[datetime]
    ) -> None:
        self._update_findings_map(result, committed_datetime, self._baseline_map)

    def update_current(
        self, result: Dict[str, Any], committed_datetime: Optional[datetime]
    ) -> None:
        self._update_findings_map(result, committed_datetime, self._current_map)

    def has_current_issues(self) -> bool:
        return len(self._current_map) > 0

    def paths_with_current_findings(self) -> Set[str]:
        return {key.path for key in self._current_map.keys()}
