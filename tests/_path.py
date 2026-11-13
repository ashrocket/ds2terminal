"""Put skills/ds-terminal-theme/scripts on sys.path so tests can import dsterm."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "ds-terminal-theme", "scripts")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
SAMPLE = os.path.join(FIXTURES, "sample")
FORMATS = os.path.join(FIXTURES, "formats")
TERMINAL = os.path.join(FIXTURES, "terminal")
# the project's own design system: light only, a strongly colored page ground
OWN = os.path.join(ROOT, "design-system", "tokens.json")
OWN_CSS = os.path.join(ROOT, "design-system", "tokens.css")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
