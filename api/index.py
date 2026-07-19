"""
Vercel serverless entry point.

@vercel/python looks for a WSGI `app` variable in this module.
The real Flask app lives one directory up.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app  # noqa: E402,F401
