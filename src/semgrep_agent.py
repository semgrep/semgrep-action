#!/usr/bin/env python
import os


def main() -> None:
    os.execlp("semgrep", "ci")


if __name__ == "__main__":
    main()
