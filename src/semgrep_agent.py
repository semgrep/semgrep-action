#!/usr/bin/env python
import os


def main() -> None:
    os.execvp("semgrep", ["semgrep", "ci"])


if __name__ == "__main__":
    main()
