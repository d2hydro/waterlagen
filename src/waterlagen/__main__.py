"""Support ``python -m waterlagen`` as well as the installed command."""

from waterlagen.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
