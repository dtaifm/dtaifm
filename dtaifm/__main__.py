"""Allow `python -m dtaifm ...` invocation in environments where the console
script isn't on PATH."""

import sys

from dtaifm.cli import main

if __name__ == "__main__":
    sys.exit(main())
