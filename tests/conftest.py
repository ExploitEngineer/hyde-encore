import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "Configs" / ".local" / "lib" / "hyde"
sys.path.insert(0, str(LIB))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
