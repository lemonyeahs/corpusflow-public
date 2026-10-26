"""Generate an offline training-center catalog using only the standard library."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from corpusflow.modules.training_center.generation import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
