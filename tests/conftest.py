"""Put `perception/` on the import path so the parser can be imported the same
way the node imports it, without installing anything."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "perception"))
