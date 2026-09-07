"""
PC Fish 智慧繁殖助手 - 跨設備全自動系統診斷工具 (System Diagnostic Tool)
執行後將自動檢測當前電腦的作業系統、Python位元、遊戲進程、記憶體權限、IL2CPP導出表與堆實例狀態，
並自動生成完整的 diagnosis_report.txt 診斷報告以供排查。
"""

import sys
import os
import platform
import ctypes
from ctypes import wintypes
import struct
import time
from datetime import datetime

# 強制 Windows 終端支援 UTF-8 輸出，避免 cp950 編碼報錯
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except:
    pass

# 加入當前目錄
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

report_lines = []

def log(msg):
    try:
        print(msg)
    except:
        try:
            print(msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'))
        except:
            pass
    report_lines.append(msg)


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def run_diagnosis():
    log("=" * 65)
    log(f"   🐟 PC Fish 跨設備全自動系統診斷報告 (Diagnostic Report)")
    log(f"   產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 65)
    log("")

    # -------------------------------------------------------------
    # 1. 系統與 Python 環境
    # -------------------------------------------------------------
    log("[ 1. 系統與 Python 執行環境 ]")
    is_64bit_os = platform.machine().endswith('64')
    is_64bit_py = sys.maxsize > 2**32
    admin = is_admin()

    log(f"  • 作業系統: {platform.system()} {platform.release()} (版本: {platform.version()})")
    log(f"  • 系統架構: {platform.machine()} (64 位元: {is_64bit_os})")
    log(f"  • Python 版本: {platform.python_version()} ({'64 位元' if is_64bit_py else '32 位元 ⚠️ (警報: 32位元無法存取64位元遊戲記憶體！)'})")
    log(f"  • 管理員權限: {'已具備 (Administrator)' if admin else '無 (建議以系統管理員權限執行)'}")
    log("")

    if not is_64bit_py:
        log("❌ 嚴重錯誤：當前使用的 Python 為 32 位元，無法讀取 64 位元遊戲 PCFish.exe 的記憶體！")
        log("   請務必在該電腦上安裝 64-bit 的 Python 3.10+。")
        log("")

    # -------------------------------------------------------------
    # 2. 遊戲進程檢測
    # -------------------------------------------------------------
    log("[ 2. 遊戲進程 (PCFish.exe) 偵測 ]")
    import psutil
    found_proc = None
    for p in psutil.process_iter(['pid', 'name', 'exe', 'create_time']):
        try:
            if p.info['name'] and p.info['name'].lower() == 'pcfish.exe':
                found_proc = p
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not found_proc:
        log("  ❌ 未檢測到 PCFish.exe 正在運行！請先啟動遊戲後再重新執行本診斷程式。")
        save_report()
        return

    pid = found_proc.info['pid']
    exe_path = found_proc.info['exe'] or '未知路徑'
    log(f"  • 成功偵測到進程: PID = {pid}")
    log(f"  • 遊戲執行檔路徑: {exe_path}")
    log("")

    # -------------------------------------------------------------
    # 3. 記憶體句柄與權限測試
    # -------------------------------------------------------------
    log("[ 3. 記憶體控制權限與句柄 (OpenProcess) ]")
    kernel32 = ctypes.windll.kernel32
    PROCESS_ALL_ACCESS = 0x1F0FFF
    PROCESS_VM_READ = 0x0010
    PROCESS_VM_WRITE = 0x0020
    PROCESS_VM_OPERATION = 0x0008
    PROCESS_QUERY_INFORMATION = 0x0400

    flags = PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION
    h_proc = kernel32.OpenProcess(flags, False, pid)
    last_err = kernel32.GetLastError()

    if not h_proc:
        log(f"  ❌ 無法開啟遊戲進程句柄！Win32 錯誤代碼: {last_err}")
        if last_err == 5:
            log("     原因: 拒絕存取 (Access Denied)。請嘗試以「系統管理員身分」運行本工具！")
        save_report()
        return

    log(f"  • 成功取得遊戲進程句柄 Handle: {h_proc}")
    log("")

    # -------------------------------------------------------------
    # 4. GameAssembly.dll 模組與導出表分析
    # -------------------------------------------------------------
    log("[ 4. GameAssembly.dll 模組與 IL2CPP 導出函式分析 ]")
    from pcfish_core import PCFishMemory, MBI, MEM_COMMIT, MEM_PRIVATE
    core = PCFishMemory()
    core.pid = pid
    core.h_proc = h_proc

    ga_base = core.get_module_base("GameAssembly.dll")
    if not ga_base:
        log("  ❌ 無法於進程中定位 GameAssembly.dll 模組！")
        save_report()
        return

    log(f"  • GameAssembly.dll 模組基址 (Base Address): {hex(ga_base)}")

    # 導出表分析
    exports = core.get_il2cpp_exports()
    log(f"  • IL2CPP 核心導出函式解析數量: {len(exports) if exports else 0}")
    if exports:
        for fn, addr in sorted(exports.items()):
            log(f"    - {fn}: {hex(addr)}")
    else:
        log("  ❌ 無法解析 IL2CPP 導出函式！")

    log("")

    # -------------------------------------------------------------
    # 5. 遠程線程與安全防護攔截檢測 (CreateRemoteThread)
    # -------------------------------------------------------------
    log("[ 5. 遠程執行與防毒安全攔截檢測 (Remote Execution Check) ]")
    sc_test = bytearray(b'\xB8\x2A\x00\x00\x00\xC3') # mov eax, 42; ret
    test_code_addr = kernel32.VirtualAllocEx(ctypes.c_void_p(h_proc), None, len(sc_test), 0x3000, 0x40)
    if not test_code_addr:
        log(f"  ❌ VirtualAllocEx 記憶體空間配置失敗！Win32 錯誤碼: {kernel32.GetLastError()}")
    else:
        written = ctypes.c_size_t()
        kernel32.WriteProcessMemory(ctypes.c_void_p(h_proc), ctypes.c_void_p(test_code_addr), bytes(sc_test), len(sc_test), ctypes.byref(written))
        h_th = kernel32.CreateRemoteThread(ctypes.c_void_p(h_proc), None, 0, ctypes.c_void_p(test_code_addr), None, 0, None)
        th_err = kernel32.GetLastError()
        if not h_th:
            log(f"  ❌ CreateRemoteThread 被系統或防毒軟體攔截！錯誤代碼: {th_err}")
            log("     (若錯誤碼為 5 拒絕存取，代表 Windows Defender Exploit Guard 或第三方防毒軟體封鎖了跨進程線程)")
        else:
            kernel32.WaitForSingleObject(h_th, 3000)
            exit_code = ctypes.c_ulong()
            kernel32.GetExitCodeThread(h_th, ctypes.byref(exit_code))
            log(f"  • 遠程線程執行能力: 正常 (ExitCode = {exit_code.value})")
            kernel32.CloseHandle(h_th)
        kernel32.VirtualFreeEx(ctypes.c_void_p(h_proc), ctypes.c_void_p(test_code_addr), 0, 0x8000)
    log("")

    # -------------------------------------------------------------
    # 6. IL2CPP 類別動態解析 (Class Resolution)
    # -------------------------------------------------------------
    log("[ 6. 核心類別動態解析 (GameDataManager / FishModel / UIBreed) ]")
    t0 = time.time()
    ok_res, msg_res = core.resolve_il2cpp_classes()
    t_elapsed = time.time() - t0

    if ok_res:
        log(f"  • 動態解析狀態: 成功 (耗時 {t_elapsed:.3f} 秒)")
        log(f"    - GameDataManager klass: {hex(core.gamedata_klass or 0)}")
        log(f"    - FishModel klass:       {hex(core.fish_model_klass or 0)}")
        log(f"    - UIBreed klass:         {hex(core.uibreed_klass or 0)}")
    else:
        log(f"  ❌ 動態解析失敗: {msg_res}")

    log("")

    # -------------------------------------------------------------
    # 7. 堆記憶體與 GameDataManager 候選者深度診斷
    # -------------------------------------------------------------
    log("[ 7. 堆記憶體與 GameDataManager 實例掃描診斷 ]")
    if not core.gamedata_klass:
        log("  ⚠️ 因未能取得 gamedata_klass，跳過單例深度掃描。")
    else:
        target = struct.pack('<Q', core.gamedata_klass)
        mbi = MBI()
        addr = 0
        total_matched = 0
        accepted_inst = None
        rejection_reasons = []

        while kernel32.VirtualQueryEx(h_proc, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            if mbi.State == MEM_COMMIT and not (mbi.Protect & 0x100) and not (mbi.Protect & 0x01):
                chunk = 65536
                for off in range(0, size, chunk):
                    to_read = min(chunk + 8, size - off)
                    buf = core.read_bytes(base + off, to_read)
                    pos = 0
                    while True:
                        p = buf.find(target, pos)
                        if p == -1: break
                        cand = base + off + p
                        total_matched += 1

                        hearts = core.read_i32(cand + 0x40)
                        fl = core.read_ptr(cand + 0x68)
                        is_private = (mbi.Type == MEM_PRIVATE)

                        details = f"Cand: {hex(cand)} | Type: {'MEM_PRIVATE' if is_private else hex(mbi.Type)} | Hearts: {hearts} | fl: {hex(fl) if fl else None}"

                        # 檢查排除原因
                        if not is_private:
                            rejection_reasons.append(f"{details} -> 排除: 非 MEM_PRIVATE 堆區域 (可能為模組鏡像或對應檔)")
                        elif hearts is None or not (0 <= hearts <= 10):
                            rejection_reasons.append(f"{details} -> 排除: 愛心數值異常 ({hearts})")
                        elif not fl:
                            rejection_reasons.append(f"{details} -> 排除: fishList 指針為空")
                        elif not (0x10000 <= fl <= 0x7FFFFFFFFFFF):
                            rejection_reasons.append(f"{details} -> 排除: fishList 指針超出有效範圍 ({hex(fl)})")
                        else:
                            count = core.read_i32(fl + 0x18)
                            items = core.read_ptr(fl + 0x10)
                            tank_lvl = core.read_i32(cand + 0x38)
                            if count is None or count <= 0 or count > 5000:
                                rejection_reasons.append(f"{details} -> 排除: 魚庫數量異常或為空 ({count})")
                            elif not items:
                                rejection_reasons.append(f"{details} -> 排除: 魚庫陣列指針為空")
                            elif tank_lvl is not None and tank_lvl < 1:
                                rejection_reasons.append(f"{details} -> 排除: 魚缸等級為 0 (未初始化實例)")
                            else:
                                accepted_inst = cand
                                rejection_reasons.append(f"{details} -> ✅ 符合所有條件！已選定為有效單例！")
                                break
                        pos = p + 8
                    if accepted_inst: break
                if accepted_inst: break
            addr = base + size
            if addr >= 0x7FFFFFFFFFFF: break

        log(f"  • 記憶體中匹配到指針頭部個數: {total_matched}")
        log(f"  • 最終定位單例: {hex(accepted_inst) if accepted_inst else '❌ 查無有效實例 (None)'}")
        log("")
        log("  [ 候選物件逐一分析日誌 (前 10 筆) ]:")
        for r in rejection_reasons[:10]:
            log(f"    • {r}")
        if len(rejection_reasons) > 10:
            log(f"    ... 總共 {len(rejection_reasons)} 筆分析紀錄")
        log("")

    # -------------------------------------------------------------
    # 8. 即時數據讀取測試
    # -------------------------------------------------------------
    log("[ 8. 即時數據讀取實測 (Hearts & Fish Inventory) ]")
    gdm = core.locate_gamedata_manager()
    if gdm:
        saved_h = core.read_i32(gdm + 0x40) or 0
        last_ts = core.read_i64(gdm + 0x48) or 0
        tank_lvl = core.read_i32(gdm + 0x38) or 0
        hearts, timer_str, is_valid, target_ts = core.get_breed_heart_status()
        log(f"  • 記憶體底層數值: 存檔愛心={saved_h} | 魚缸等級={tank_lvl} | 時間戳={last_ts}")
        log(f"  • 動態愛心計算: {hearts} 顆 | 計時倒數: {timer_str} | 目標時間戳={target_ts} | 有效性={is_valid}")
        fishes = core.get_all_fish()
        log(f"  • 魚庫清單: 成功讀取 {len(fishes)} 隻魚")
        if fishes:
            log(f"    範例第一隻魚: [{fishes[0]['rarity']}] {fishes[0]['name']} (星級: {fishes[0]['stars']}, 配種: {fishes[0]['breed']}/{fishes[0]['breed_max']})")
    else:
        log("  ❌ GameDataManager 未能成功定位，無法讀取愛心與魚隻！")

    u = core.locate_uibreed()
    if u:
        txt_ptr = core.read_ptr(u + 0x30)
        scr_text = ""
        if txt_ptr:
            s_ptr = core.read_ptr(txt_ptr + 0xe0)
            if s_ptr:
                scr_text = core.read_utf16_str(s_ptr) or ""
        log(f"  • UIBreed (繁殖面板): 定位成功 ({hex(u)}) | 遊戲畫面文字: \"{scr_text}\"")
    else:
        log(f"  • UIBreed (繁殖面板): 未開啟 (請在遊戲中打開繁殖面板)")
    log("")

    # -------------------------------------------------------------
    # 9. 綜合診斷總結與建議
    # -------------------------------------------------------------
    log("=" * 65)
    log("   📋 綜合診斷結論與排查建議")
    log("=" * 65)

    if not is_64bit_py:
        log("1. ⚠️ 【Python 位元錯誤】: 當前使用的是 32-bit Python，無法控制 64-bit 遊戲，請安裝 64-bit Python。")
    elif not admin:
        log("1. 💡 【權限建議】: 目前未使用管理員身分運行，若遊戲由 Steam 啟動且具較高權限，可能造成記憶體存取受限，建議右鍵選擇「以系統管理員身分執行」。")
    elif not core.gamedata_klass:
        log("1. ⚠️ 【IL2CPP 解析受阻】: 無法建立遠程線程解析類別，可能是防毒軟體或 Windows 安全性攔截，請暫時將此工具加入防毒排除名單。")
    elif not gdm:
        log("1. ⚠️ 【實例未能在堆中找到】: 請檢查上述「候選物件逐一分析日誌」，確認指針是否因範圍過濾而被排除。")
    else:
        log("🎉 【系統完全正常】: 所有類別、指針鏈、愛心狀態與魚庫清單皆已 100% 成功讀取！")

    log("")
    log(f"報告已成功保存至: {os.path.abspath('diagnosis_report.txt')}")
    save_report()

def save_report():
    out_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'diagnosis_report.txt')
    try:
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
    except Exception as e:
        print(f"寫入報告失敗: {e}")

if __name__ == "__main__":
    run_diagnosis()
