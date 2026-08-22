import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "corpus" / "examples"
FIXTURES = ROOT / "tests" / "fixtures"
CLEAN_DOCUMENT = CORPUS / "container" / "documentcontainer.zip"
CLEAN_DOCUMENTATION = CORPUS / "container" / "documentationcontainer.zip"
