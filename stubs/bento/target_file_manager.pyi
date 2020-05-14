from pathlib import Path
from typing import Any, List, Optional

class TargetFileManager:
    def __init__(
        self,
        base_path: Path,
        paths: List[Path],
        staged: bool,
        ignore_rules_file_path: Path,
        base_commit: str = "HEAD",
        status: Any = None,
        target_paths: Optional[List[Path]] = None,
    ) -> None: ...
    @property
    def _target_paths(self) -> List[Path]: ...
