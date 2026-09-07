import sys
import os
import json

def register():
    cwd = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        r"g:\python\toolLauncher\resources\config\registry.json",
        os.path.abspath(os.path.join(cwd, "..", "toolLauncher", "resources", "config", "registry.json")),
        os.path.abspath(os.path.join(cwd, "..", "..", "toolLauncher", "resources", "config", "registry.json")),
        os.path.abspath(os.path.join(cwd, "..", "resources", "config", "registry.json")),
    ]
    reg_path = next((p for p in candidates if os.path.exists(p)), None)
    if not reg_path:
        print("[Warning] 未找到 AI Tool Launcher 註冊表路徑。")
        return

    try:
        with open(reg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Error] 讀取註冊表失敗: {e}")
        return

    exec_path = os.path.normpath(os.path.join(cwd, "main.py"))
    tools = [t for t in data.get("tools", []) if os.path.normpath(t.get("executable", "")).lower() != exec_path.lower()]
    tools.append({
        "name": "PC Fish 智能繁殖管理終端",
        "repo_name": "Auto-PCFish",
        "description": "PC Fish 全自動記憶體直讀繁殖、同階與差一階智能配種、無感差量更新與本地計時休眠工具",
        "executable": exec_path,
        "working_dir": cwd
    })
    data["tools"] = tools

    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    try:
        print(f"[OK] 成功註冊「PC Fish 智能繁殖管理終端」至啟動器！路徑: {exec_path}")
    except:
        print(f"[OK] Successfully registered to AI Tool Launcher! Path: {exec_path}")

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    register()
