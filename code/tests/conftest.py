"""Make each tool directory importable (several have hyphens, so they are not packages)."""
import os
import sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("discovery", "classification", "envelope", "tokenization", "crypto-shredding", "cbom"):
    path = os.path.join(CODE_DIR, sub)
    if path not in sys.path:
        sys.path.insert(0, path)
