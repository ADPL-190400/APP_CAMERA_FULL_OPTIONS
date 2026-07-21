import os
import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()

def get_model_path(filename):
    return os.path.join(BASE_DIR, "process", "models", filename)
