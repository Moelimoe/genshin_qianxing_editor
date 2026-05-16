# -*- coding: utf-8 -*-
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.absolute()
DEBUG = bool(os.getenv("DEBUG", "0") == "1")
