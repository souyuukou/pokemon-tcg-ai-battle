import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "sample_submission"
sys.path.insert(0, str(ROOT))

from pvs_bridge import bridge

deck = [int(x) for x in (ROOT / "deck.csv").read_text().split() if x.strip()]
print("init", bridge.initialize(deck), bridge.error)
