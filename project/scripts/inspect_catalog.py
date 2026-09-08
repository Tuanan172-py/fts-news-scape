# -*- coding: utf-8 -*-
import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.agent.entities import load_registry

reg = load_registry()
print("Registry successfully loaded. Total entities:", len(reg.entities))
