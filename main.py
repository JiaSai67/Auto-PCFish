"""
PC Fish 智能繁殖管理終端 - 主程式入口 (Main Entrypoint)
符合 AIToolLauncher 標準微型專案規範
"""

import sys
import os

# 確保當前目錄在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from auto_breed_gui import AutoBreedApp

VERSION = "1.0.5"

def main():
    print(f"=== PC Fish 智能繁殖管理終端 v{VERSION} ===")
    root = tk.Tk()
    app = AutoBreedApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
