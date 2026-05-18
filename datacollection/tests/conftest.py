import sys
import os

FREEARK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if FREEARK_ROOT not in sys.path:
    sys.path.insert(0, FREEARK_ROOT)
