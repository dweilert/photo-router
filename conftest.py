import sys
from pathlib import Path

# Add project root to sys.path so 'app' is importable
root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
