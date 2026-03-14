"""Vercel serverless entry point — exposes the Flask app as a WSGI handler."""

import os
import sys

# Add src/ to Python path so auto_goldfish package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from auto_goldfish.web import create_app

app = create_app()
