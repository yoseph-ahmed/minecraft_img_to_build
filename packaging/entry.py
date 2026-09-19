"""PyInstaller entry point. Kept separate so the package stays importable."""

import multiprocessing
import sys

from mcbuilder.cli import frozen_main

if __name__ == "__main__":
    # Without this, a frozen process that ever spawns a child re-runs the
    # whole program in it. Cheap insurance, required before anything else.
    multiprocessing.freeze_support()
    sys.exit(frozen_main())
