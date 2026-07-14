"""Allow ``python -m judgecal`` as an alias for the ``judgecal`` script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
