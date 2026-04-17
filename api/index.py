import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
GUI_DIR = os.path.join(ROOT_DIR, "GUI")

if GUI_DIR not in sys.path:
    sys.path.insert(0, GUI_DIR)

from MAIN import app
