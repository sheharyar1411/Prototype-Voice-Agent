"""
Voice AI Patient Registration System — Application Package.

A FastAPI-based REST API with Vapi voice AI integration for automated
patient demographic intake via phone calls.
"""

import os
import sys

# Ensure backend root is on sys.path so submodules resolve under all entry points
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

__version__ = "1.0.0"
