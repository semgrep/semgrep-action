import fnmatch
import os
import re
import time
from pathlib import Path
from typing import Collection
from typing import Dict
from typing import Iterable
from typing import Iterator
from typing import List
from typing import Mapping
from typing import Set
from typing import TextIO

import attr
import click

from .utils import debug_echo

CONTROL_REGEX = re.compile(r"(?!<\\):")  # Matches unescaped colons
MULTI_CHAR_REGEX = re.compile(
    r"(?!<\\)\[.*(?!<\\)\]"
)  # Matches anything in unescaped brackets
COMMENT_START_REGEX = re.compile(r"(?P<ignore_pattern>.*?)(?:\s+|^)#.*")
IGNORE_FILE_NAME = ".semgrepignore"


@attr.s
class Entry:
    path = attr.ib(type=Path)
    survives = attr.ib(type=bool)


@attr.s(auto_attribs=True)
class WalkEntries(Collection[Entry]):
    cache: Dict[Path, Entry]

    def __len__(self) -> int:
        return len(self.cache)

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.cache.values())

    def __contains__(self, item: object) -> bool:
        return isinstance(item, Entry) and item.path in self.cache


@attr.s
class FileIgnore(Mapping[Path, Entry]):
    base_path = attr.ib(type=Path)
    patterns = attr.ib(type=Set[str])
    target_paths = attr.ib(type=List[Path])
    _processed_patterns = attr.ib(type=Set[str], init=False)
    _walk_cache: Dict[Path, Entry] = attr.ib(default=None, init=False)

    def __attrs_post_init__(self) -> None:
        self._processed_patterns = Processor(self.base_path).process(self.patterns)
        self._init_cache()

    def _survives(self, path: Path) -> bool:
        """
        Determines if a single Path survives the ignore filter.
        """
        for p in self._processed_patterns:
            if path.is_dir() and p.endswith("/") and fnmatch.fnmatch(str(path), p[:-1]):
                return False
            if fnmatch.fnmatch(str(path), p):
                return False

            # Check any subpath of path satisfies a pattern
            # i.e. a/b/c/d is ignored with rule a/b
            # This is a hack. TargetFileManager should be pruning while searching
            # instead of post filtering to avoid this
            # Note: Use relative to base to avoid ignore rules firing on parent directories
            # i.e. /private/var/.../instabot should not be ignored with var/ rule
            # in instabot dir as base_path
            # Note: Append "/" to path before running fnmatch so **/pattern matches with pattern/stuff
            if p.endswith("/") and fnmatch.fnmatch(
                "/" + str(path.relative_to(self.base_path)), p + "*"
            ):
                return False
            if (
                p.endswith("/")
                and p.startswith(str(self.base_path))
                and fnmatch.fnmatch(str(path), p + "*")
            ):
                return False

        return True

    def _walk(self, this_path: str, root_path: str) -> Iterator[Entry]:
        """
        Walks path, returning an Entry iterator for each item.

        If an item is not ignored, it is traversed recursively. Traversal stops on
        ignored items.

        Recalculates on every call.
        """
        # Handle non existent paths passed to cli.
        # TODO handle further up
        if not Path(this_path).exists():
            return

        if Path(this_path).is_file():
            yield Entry(Path(this_path), self._survives(Path(this_path)))
        else:
            for e in os.scandir(this_path):
                if e.is_symlink():
                    continue
                elif self._survives(Path(e.path)):
                    before = time.time()
                    for ee in self._walk(e.path, root_path):
                        yield ee
                    filename = Path(this_path) / e.name
                else:
                    # TODO I think we can remove the false ones and have existence be survival
                    yield Entry(Path(e.path), False)

    def _init_cache(self) -> None:
        debug_echo(f"Ignored patterns are:\n{self.patterns}")
        before = time.time()
        self._walk_cache = {}
        for target in self.target_paths:
            entries = self._walk(str(target), str(self.base_path))
            self._walk_cache.update(dict((e.path, e) for e in entries))
        debug_echo(f"Loaded file ignore cache in {time.time() - before} s.")

    def entries(self) -> Collection[Entry]:
        """
        Returns all files that are not ignored, relative to the base path.
        """
        return WalkEntries(self._walk_cache)

    def filter_paths(self, paths: Iterable[Path]) -> List[Path]:
        abspaths = (p.absolute() for p in paths if p.exists())
        return [
            p
            for p in abspaths
            if p in self and self[p].survives or p.samefile(self.base_path)
        ]

    def __getitem__(self, item: Path) -> Entry:
        return self._walk_cache[item]

    def __iter__(self) -> Iterator[Path]:
        return iter(self._walk_cache)

    def __len__(self) -> int:
        return len(self._walk_cache)

    def __contains__(self, item: object) -> bool:
        return item in self._walk_cache


@attr.s(auto_attribs=True)
class Parser:
    """
    A parser for semgrepignore syntax.

    semgrepignore syntax mirrors gitignore syntax, with the following modifications:
    - "Include" patterns (lines starting with "!") are not supported.
    - "Character range" patterns (lines including a collection of characters inside brackets) are not supported.
    - An ":include ..." directive is added, which allows another file to be included in the ignore pattern list;
      typically this included file would be the project .gitignore. No attempt at cycle detection is made.
    - Any line beginning with a colon, but not ":include ", will raise a ValueError.
    - "\:" is added to escape leading colons.

    Unsupported patterns are silently removed from the pattern list (this is done so that gitignore files may be
    included without raising errors), although the removal will be logged.

    Unfortunately there's no available parser for gitignore syntax in python, so we have
    to make our own. The syntax is simple enough that we can just roll our own parser, so
    I deliberately skip using a parser generator or combinator library, which would either need to
    parse on a character-by-character basis or make use of a large number of regex scans.

    The parser steps are, for each line in the input stream:
    1. Remove comments
    2. Remove unsupported gitignore syntax
    3. Expand directives

    The end result of this parsing is a set of human-readable patterns corresponding to gitignore syntax.
    To use these patterns with fnmatch, however, a final postprocessing step is needed, achieved by calling
    Processor.process().

    :param base_path:   The path relative to which :include directives should be evaluated
    """

    # Parser steps are each represented as Generators. This allows us to chain
    # steps, whether the step is a transformation, a filter, an expansion, or any combination thereof.

    base_path: Path

    @staticmethod
    def remove_comments(line: str) -> Iterator[str]:
        """If a line has a comment, remove the comment and just return the ignore pattern
        """
        m = COMMENT_START_REGEX.match(line)
        if m:
            yield m.groupdict().get(
                "ignore_pattern", ""
            )  # return empty string if entire line is a comment
        else:
            yield line.rstrip()

    @staticmethod
    def filter_supported(line: str) -> Iterator[str]:
        """Remove unsupported gitignore patterns"""
        if not line:
            pass
        elif line.startswith("!") or MULTI_CHAR_REGEX.search(line):
            debug_echo(f"Skipping unsupported gitignore pattern '{line}'")
        else:
            yield line

    def expand_directives(self, line: str) -> Iterable[str]:
        """Load :include files"""
        if line.startswith(":include "):
            include_path = self.base_path / line[9:]
            if include_path.is_file():
                with include_path.open() as include_lines:
                    sub_base = include_path.parent.resolve()
                    sub_parser = Parser(sub_base)
                    return sub_parser.parse(include_lines)
            else:
                debug_echo(
                    f"Skipping `:include {include_path}` directive, file not found"
                )
                return []
        elif CONTROL_REGEX.match(line):
            raise ValueError(f"Unknown ignore directive: '{line}'")
        else:
            return (line for _ in range(1))

    def parse(self, stream: TextIO) -> Set[str]:
        """Performs parsing of an input stream"""
        return {
            pattern
            for line in stream
            for no_comments in self.remove_comments(line)
            for supported in self.filter_supported(no_comments)
            for pattern in self.expand_directives(supported)
        }


@attr.s(auto_attribs=True)
class Processor:
    """
    A post-processor for parsed semgrepignore files.

    The postprocessor is responsible for converting the parser's intermediate representation to a set of
    patterns compatible with fnmatch. The steps are:
    1. Unescape escape characters
    2. Convert gitignore patterns into fnmatch patterns
    """

    # Per Parser, each Processor step is represented as a Generator.

    base_path: Path

    @staticmethod
    def unescape(line: str) -> Iterator[str]:
        """Expands escape characters"""
        out = ""
        is_escape = False
        for c in line:
            if is_escape:
                out += c
                is_escape = False
            elif c == "\\":
                is_escape = True
            else:
                out += c
        yield out

    def to_fnmatch(self, pat: str) -> Iterator[str]:
        """Convert a single pattern from gitignore to fnmatch syntax"""
        if pat.rstrip("/").find("/") < 0:
            # Handles:
            #   file
            #   path/
            pat = os.path.join("**", pat)
        if pat.startswith("./") or pat.startswith("/"):
            # Handles:
            #   /relative/to/root
            #   ./relative/to/root
            pat = pat.lstrip(".").lstrip("/")
        if not pat.startswith("**"):
            # Handles:
            #   path/to/absolute
            #   */to/absolute
            #   path/**/absolute
            pat = os.path.join(self.base_path, pat)
        yield pat

    def process(self, pre: Iterable[str]) -> Set[str]:
        """Post-processes an intermediate representation"""
        return {
            pattern
            for pat in pre
            for unescaped in self.unescape(pat)
            for pattern in self.to_fnmatch(unescaped)
        }
