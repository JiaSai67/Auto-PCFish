"""
PC Fish 智能繁殖管理終端 - 主程式入口 (Main Entrypoint)
符合 AIToolLauncher 標準微型專案規範
"""

import sys
import os

# Windows CP950 終端編碼保護 (杜絕 UnicodeEncodeError 閃退)
if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

# 確保當前目錄在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from auto_breed_gui import AutoBreedApp

VERSION = "1.0.7 STABLE"

def main():
    print(f"=== PC Fish 智能繁殖管理終端 v{VERSION} ===")
    root = tk.Tk()
    app = AutoBreedApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
