import subprocess
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

from semgrep_agent.constants import GIT_SH_TIMEOUT
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
class PathLists:
    targeted = attr.ib(type=List[Path])
    ignored = attr.ib(type=List[Path])


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
    _all_paths = attr.ib(type=List[Path])
    _ignore_rules_file = attr.ib(type=TextIO)
    _base_commit = attr.ib(type=Optional[str], default=None)
    _status = attr.ib(type=GitStatus, init=False)
    _paths = attr.ib(type=PathLists, init=False)

    _dirty_paths_by_status: Optional[Dict[str, List[Path]]] = None

    def _fname_to_path(self, repo: "gitpython.Repo", fname: str) -> Path:  # type: ignore
        debug_echo(f"_fname_to_path: root: {repo.working_tree_dir} fname: {fname}")
        return (Path(repo.working_tree_dir) / fname).resolve()

    @_status.default
    def get_git_status(self) -> GitStatus:
        """
        Returns Absolute Paths to all files that are staged

        Ignores files that are symlinks to directories
        """
        import gitdb.exc  # type: ignore

        debug_echo("Initializing git status")
        repo = get_git_repo()

        if not repo or self._base_commit is None:
            debug_echo("Not repo or no base_commit")
            return GitStatus([], [], [], [])

        try:
            repo.rev_parse(self._base_commit)
        except gitdb.exc.BadName:
            raise ActionFailure(f"Unknown git ref '{self._base_commit}'")

        # Output of git command will be relative to git project root
        debug_echo("Running git diff")
        status_output = zsplit(
            git.diff(
                "--cached",
                "--name-status",
                "--no-ext-diff",
                "-z",
                "--diff-filter=ACDMRTUXB",
                "--ignore-submodules",
                "--merge-base",
                self._base_commit,
                _timeout=GIT_SH_TIMEOUT,
            ).stdout.decode()
        )
        debug_echo("Finished git diff. Parsing git status output")
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
                    f"| Skipping {absolute_name} since it is a symlink to a directory: {resolved_name}",
                    err=True,
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
                    added.append(self._fname_to_path(repo, fname))
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

    @_paths.default
    def _get_path_lists(self) -> PathLists:
        """
        Return list of all absolute paths to analyze
        """
        debug_echo("Getting path list")

        # resolve given paths relative to current working directory
        debug_echo(f"resolving all_paths: {self._all_paths}")
        paths = [p.resolve() for p in self._all_paths]

        if self._base_commit is not None:
            debug_echo(f"- base_commit is {self._base_commit}")
            paths = [
                a
                for a in (self._status.added + self._status.modified)
                # diff_path is a subpath of some element of input_paths
                if any((a == path or path in a.parents) for path in paths)
            ]
            changed_count = len(paths)
            click.echo(f"| looking at {unit_len(paths, 'changed path')}", err=True)
            repo = get_git_repo()
            debug_echo("Got git repo")
            submodules = repo.submodules  # type: ignore
            debug_echo(f"Resolving submodules {submodules}")
            submodule_paths = [
                self._fname_to_path(repo, submodule.path) for submodule in submodules
            ]
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
        debug_echo("Reset ignores file")
        self._ignore_rules_file.seek(0)
        debug_echo("Parsing ignore_rules_file")
        patterns = Parser(self._base_path).parse(self._ignore_rules_file)
        debug_echo("Parsed ignore rules")

        file_ignore = FileIgnore(
            base_path=self._base_path, patterns=patterns, target_paths=paths
        )
        debug_echo("Initialized FileIgnore")

        walked_entries = list(file_ignore.entries())
        click.echo(
            f"| found {unit_len(walked_entries, 'file')} in the paths to be scanned",
            err=True,
        )
        survived_paths: List[Path] = []
        ignored_paths: List[Path] = []
        for elem in walked_entries:
            paths_group = survived_paths if elem.survives else ignored_paths
            paths_group.append(elem.path)

        if ignored_paths:
            click.echo(
                f"| skipping {unit_len(ignored_paths, 'file')} based on path ignore rules",
                err=True,
            )

            for p in patterns:
                debug_echo(f"Ignoring files matching pattern '{p}'")

        relative_survived_paths = [
            path.relative_to(self._base_path) for path in survived_paths
        ]
        relative_ignored_paths = [
            path.relative_to(self._base_path) for path in ignored_paths
        ]
        debug_echo("Finished initializing path list")

        return PathLists(
            targeted=relative_survived_paths, ignored=relative_ignored_paths
        )

    def get_dirty_paths_by_status(self) -> Dict[str, List[Path]]:
        """
        Returns all paths that have a git status, grouped by change type.

        These can be staged, unstaged, or untracked.
        """
        if self._dirty_paths_by_status is not None:
            return self._dirty_paths_by_status

        debug_echo("Initializing dirty paths")
        sub_out = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            timeout=GIT_SH_TIMEOUT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        git_status_output = sub_out.stdout.decode("utf-8", errors="replace")
        debug_echo(f"Git status output: {git_status_output}")
        output = zsplit(git_status_output)
        debug_echo("finished getting dirty paths")

        dirty_paths = bucketize(
            output,
            key=lambda line: line[0],
            value_transform=lambda line: Path(line[3:]),
        )
        debug_echo(str(dirty_paths))

        # Cache dirty paths
        self._dirty_paths_by_status = dirty_paths
        return dirty_paths

    def _abort_on_pending_changes(self) -> None:
        """
        Raises ActionFailure if any tracked files are changed.

        :raises ActionFailure: If the git repo is not in a clean state
        """
        if set(self.get_dirty_paths_by_status()) - {StatusCode.Untracked}:
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
            for path in (self.get_dirty_paths_by_status().get(StatusCode.Untracked, []))
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

        debug_echo("Running git write-tree")
        current_tree = git("write-tree").stdout.decode().strip()
        try:
            for a in self._status.added:
                try:
                    a.unlink()
                except FileNotFoundError:
                    click.echo(f"| {a} was not found when trying to delete", err=True)

            debug_echo("Running git checkout for baseline context")
            git.checkout(self._base_commit, "--", ".", _timeout=GIT_SH_TIMEOUT)
            debug_echo("Finished git checkout for baseline context")
            yield
        finally:
            # git checkout will fail if the checked-out index deletes all files in the repo
            # In this case, we still want to continue without error.
            # Note that we have no good way of detecting this issue without inspecting the checkout output
            # message, which means we are fragile with respect to git version here.
            try:
                debug_echo("Running git checkout to return original context")
                git.checkout(current_tree.strip(), "--", ".", _timeout=GIT_SH_TIMEOUT)
                debug_echo("Finished git checkout to return original context")
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
                    debug_echo("Running git rm")
                    git.rm("-f", *(str(r) for r in to_remove), _timeout=GIT_SH_TIMEOUT)
                    debug_echo("finished git rm")

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
                    for relative_path in self._paths.targeted
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
        yield self._paths.targeted

    @property
    def searched_paths(self) -> List[Path]:
        """
        The list of paths that have been searched with Semgrep

        :return: A list of paths NOT ignored, all relative to root directory
        """
        return self._paths.targeted
