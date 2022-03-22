#!/usr/bin/env python
import subprocess


def main() -> None:
    subprocess.call(["semgrep", "ci"])


if __name__ == "__main__":
    main()
