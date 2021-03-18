from collections import namedtuple
from contextlib import contextmanager
from enum import auto
from enum import Enum
from pathlib import Path
from typing import Dict
from typing import Iterator
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import TextIO
from typing import TYPE_CHECKING

import attr
import click
import sh
from boltons.iterutils import bucketize
from boltons.strutils import unit_len
from sh.contrib import git

from semgrep_agent.exc import ActionFailure
from semgrep_agent.ignores import FileIgnore
from semgrep_agent.ignores import Parser
from semgrep_agent.utils import debug_echo
from semgrep_agent.utils import get_git_repo
from semgrep_agent.utils import zsplit


if TYPE_CHECKING:
    # Only import when type checking to avoid loading module when unecessary
    import git as gitpython  # noqa


class GitStatus(NamedTuple):
    added: List[Path]
    modified: List[Path]
    removed: List[Path]
    unmerged: List[Path]


class StatusCode:
    Added = "A"
    Deleted = "D"
    Renamed = "R"
    Modified = "M"
    Unmerged = "U"
    Ignored = "!"
    Untracked = "?"
    Unstaged = " "  # but changed


@attr.s
class TargetFileManager:
    """
    Handles all logic related to knowing what files to run on.

    This includes:
        - understanding files are ignores based on semgrepignore rules
        - traversing project directories
        - pruning traversal
        - listing staged files
        - changing git state

    Parameters:
        base_commit: Git ref to compare against
        base_path: Path to start walking files from
        paths: List of Paths (absolute or relative to current working directory) that
                we want to traverse
        ignore_rules_file: Text buffer with .semgrepignore rules
    """

    _base_path = attr.ib(type=Path)
    _paths = attr.ib(type=List[Path])
    _ignore_rules_file = attr.ib(type=TextIO)
    _base_commit = attr.ib(type=Optional[str], default=None)
    _status = attr.ib(type=GitStatus, init=False)
    _target_paths = attr.ib(type=List[Path], init=False)
    _dirty_paths_by_status = attr.ib(type=Dict[str, List[Path]], init=False)

    def _fname_to_path(self, repo: "gitpython.Repo", fname: str) -> Path:  # type: ignore
        return (Path(repo.working_tree_dir) / fname).resolve()

    @_status.default
    def get_git_status(self) -> GitStatus:
        """
        Returns Absolute Paths to all files that are staged

        Ignores files that are symlinks to directories
        """
        import gitdb.exc  # type: ignore

        repo = get_git_repo()

        if not repo or self._base_commit is None:
            return GitStatus([], [], [], [])

        try:
            repo.rev_parse(self._base_commit)
        except gitdb.exc.BadName:
            raise ActionFailure(f"Unknown git ref '{self._base_commit}'")

        # Output of git command will be relative to git project root
        status_output = zsplit(
            git.diff(
                "--cached",
                "--name-status",
                "--no-ext-diff",
                "-z",
                "--diff-filter=ACDMRTUXB",
                "--ignore-submodules",
                self._base_commit,
            ).stdout.decode()
        )

        added = []
        modified = []
        removed = []
        unmerged = []
        while status_output:
            code = status_output[0]
            fname = status_output[1]
            trim_size = 2

            if not code.strip():
                continue
            if code == StatusCode.Untracked or code == StatusCode.Ignored:
                continue

            resolved_name = self._fname_to_path(repo, fname)

            # If file is symlink to directory, skip
            absolute_name = Path(repo.working_tree_dir) / fname
            if absolute_name.is_symlink() and resolved_name.is_dir():
                click.echo(
                    f"| Skipping {absolute_name} since it is a symlink to a directory: {resolved_name}"
                )
            else:
                # The following detection for unmerged codes comes from `man git-status`
                if code == StatusCode.Unmerged:
                    unmerged.append(resolved_name)
                if (
                    code[0] == StatusCode.Renamed
                ):  # code is RXXX, where XXX is percent similarity
                    removed.append(resolved_name)
                    fname = status_output[2]
                    trim_size += 1
                    added.append(resolved_name)
                if code == StatusCode.Added:
                    added.append(resolved_name)
                if code == StatusCode.Modified:
                    modified.append(resolved_name)
                if code == StatusCode.Deleted:
                    removed.append(resolved_name)

            status_output = status_output[trim_size:]
        debug_echo(
            f"Git status:\nadded: {added}\nmodified: {modified}\nremoved: {removed}\nunmerged: {unmerged}"
        )

        return GitStatus(added, modified, removed, unmerged)

    @_target_paths.default
    def _get_target_files(self) -> List[Path]:
        """
        Return list of all absolute paths to analyze
        """
        repo = get_git_repo()
        submodules = repo.submodules  # type: ignore
        submodule_paths = [
            self._fname_to_path(repo, submodule.path) for submodule in submodules
        ]

        # resolve given paths relative to current working directory
        paths = [p.resolve() for p in self._paths]
        if self._base_commit is not None:
            paths = [
                a
                for a in (self._status.added + self._status.modified)
                # diff_path is a subpath of some element of input_paths
                if any((a == path or path in a.parents) for path in paths)
            ]
            changed_count = len(paths)
            click.echo(f"| looking at {unit_len(paths, 'changed path')}", err=True)
            paths = [
                path
                for path in paths
                if all(
                    submodule_path not in path.parents
                    for submodule_path in submodule_paths
                )
            ]
            if len(paths) != changed_count:
                click.echo(
                    f"| skipping files in {unit_len(submodule_paths, 'submodule')}: "
                    + ", ".join(str(path) for path in submodule_paths),
                    err=True,
                )

        # Filter out ignore rules, expand directories
        self._ignore_rules_file.seek(0)
        patterns = Parser(self._base_path).parse(self._ignore_rules_file)

        file_ignore = FileIgnore(
            base_path=self._base_path, patterns=patterns, target_paths=paths
        )

        walked_entries = list(file_ignore.entries())
        click.echo(
            f"| found {unit_len(walked_entries, 'file')} in the paths to be scanned",
            err=True,
        )
        filtered: List[Path] = []
        for elem in walked_entries:
            if elem.survives:
                filtered.append(elem.path)

        skipped_count = len(walked_entries) - len(filtered)
        if skipped_count:
            click.echo(
                f"| skipping {unit_len(range(skipped_count), 'file')} based on path ignore rules",
                err=True,
            )

        relative_paths = [path.relative_to(self._base_path) for path in filtered]

        return relative_paths

    @_dirty_paths_by_status.default
    def get_dirty_paths_by_status(self) -> Dict[str, List[Path]]:
        """
        Returns all paths that have a git status, grouped by change type.

        These can be staged, unstaged, or untracked.
        """
        output = zsplit(git.status("--porcelain", "-z").stdout.decode())
        return bucketize(
            output,
            key=lambda line: line[0],
            value_transform=lambda line: Path(line[3:]),
        )

    def _abort_on_pending_changes(self) -> None:
        """
        Raises ActionFailure if any tracked files are changed.

        :raises ActionFailure: If the git repo is not in a clean state
        """
        if set(self._dirty_paths_by_status) - {StatusCode.Untracked}:
            raise ActionFailure(
                "Found pending changes in tracked files. Diff-aware runs require a clean git state."
            )

    def _abort_on_conflicting_untracked_paths(self) -> None:
        """
        Raises ActionFailure if untracked paths were touched in the baseline, too.

        :raises ActionFailure: If the git repo is not in a clean state
        """
        repo = get_git_repo()

        if not repo or self._base_commit is None:
            return

        changed_paths = set(
            self._status.added
            + self._status.modified
            + self._status.removed
            + self._status.unmerged
        )
        untracked_paths = {
            self._fname_to_path(repo, str(path))
            for path in (self._dirty_paths_by_status.get(StatusCode.Untracked, []))
        }
        overlapping_paths = untracked_paths & changed_paths

        if overlapping_paths:
            raise ActionFailure(
                "Some paths that changed since the baseline commit now show up as untracked files. "
                f"Please commit or stash your untracked changes in these paths: {overlapping_paths}."
            )

    @contextmanager
    def _baseline_context(self) -> Iterator[None]:
        """
        Runs a block of code on files from the current branch HEAD.

        :raises ActionFailure: If git cannot detect a HEAD commit
        :raises ActionFailure: If unmerged files are detected
        """
        repo = get_git_repo()

        if not repo:
            yield
            return

        self._abort_on_pending_changes()
        self._abort_on_conflicting_untracked_paths()

        current_tree = git("write-tree").stdout.decode().strip()
        try:
            for a in self._status.added:
                a.unlink()
            git.checkout(self._base_commit, "--", ".")
            yield
        finally:
            # git checkout will fail if the checked-out index deletes all files in the repo
            # In this case, we still want to continue without error.
            # Note that we have no good way of detecting this issue without inspecting the checkout output
            # message, which means we are fragile with respect to git version here.
            try:
                git.checkout(current_tree.strip(), "--", ".")
            except sh.ErrorReturnCode as error:
                output = error.stderr.decode()
                if (
                    output
                    and len(output) >= 2
                    and "pathspec '.' did not match any file(s) known to git"
                    in output.strip()
                ):
                    debug_echo(
                        "Restoring git index failed due to total repository deletion; skipping checkout"
                    )
                else:
                    raise ActionFailure(
                        f"Fatal error restoring Git state; please restore your repository state manually:\n{output}"
                    )

            if self._status.removed:
                # Need to check if file exists since it is possible file was deleted
                # in both the base and head. Only call if there are files to delete
                to_remove = [r for r in self._status.removed if r.exists()]
                if to_remove:
                    git.rm("-f", *(str(r) for r in to_remove))

    @contextmanager
    def baseline_paths(self) -> Iterator[List[Path]]:
        """
        Prepare file system for baseline scan, and return the paths to be analyzed.

        Returned list of paths are all relative paths and include all files that are
            - already in the baseline commit, i.e. not created later
            - not ignored based on .semgrepignore rules
            - in any path include filters specified.

        Returned list is empty if a baseline commit is inaccessible.

        :return: A list of paths
        :raises ActionFailure: If git cannot detect a HEAD commit or unmerged files exist
        """
        repo = get_git_repo()

        if not repo or self._base_commit is None:
            yield []
        else:
            with self._baseline_context():
                yield [
                    relative_path
                    for relative_path in self._target_paths
                    if self._fname_to_path(repo, str(relative_path))
                    not in self._status.added
                ]

    @contextmanager
    def current_paths(self) -> Iterator[List[Path]]:
        """
        Prepare file system for current scan, and return the paths to be analyzed.

        Returned list of paths are all relative paths and include all files that are
            - not ignored based on .semgrepignore rules
            - in any path include filters specified.

        :return: A list of paths
        :raises ActionFailure: If git cannot detect a HEAD commit or unmerged files exist
        """
        yield self._target_paths
