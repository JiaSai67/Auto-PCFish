# 🐟 PC Fish 智能繁殖管理終端 (PC Fish Auto Breed Assistant)

> 專為 PC Fish 設計的高效能、全自動記憶體直讀繁殖輔助終端。
> 支援「同階與差一階智能配種」、「無感差量更新 (In-Place Update)」、「本地 Windows 時間戳休眠喚醒」與「核心純記憶體原生繁殖訊號直發」。

---

## 🌟 核心特色

1. **⚡ 毫秒級極致效能 (0.02 秒完成確認+鎖定+繁殖)**
   - 採用 `GameDataManager + 0x68` (List<FishModel>) 64-byte 區塊單次記憶體批量讀取，解析全魚庫僅需 **14ms**。
   - `UIBreed` 實例指針簽名高速快取校驗，耗時 **0.0001ms**。
   - 純記憶體 IL2CPP 託管線程原生調用 `UIBreed.Breed()`，不搶滑鼠、不搶焦點，支援視窗後台/最小化運行。

2. **🔄 魚庫無感差量就地更新 (In-Place Delta Update)**
   - 徹底告別傳統清空重繪（`delete + insert`）導致的表單瘋狂閃爍、滾動條歸零與選取丟失問題。
   - 採用魚隻唯一識別碼比對，僅就地更新數值發生變動的欄位，操作流暢穩定。

3. **⏳ 魚種與愛心本地計時器休眠 (Zero-Load Wakeup)**
   - 愛心生成時間與魚隻冷卻時間完全採用本地時間戳比對。
   - 處於冷卻或愛心不足時，自動切換至低負載休眠模式，期間完全不消耗記憶體 I/O，時間抵達時自動精確喚醒。

4. **🛡️ 嚴格智能配種與伺服端狀態握手**
   - 嚴格遵守「原始稀有度 + 稀有度-1級」配種規則（$R_2 \in \{R_1, \max(0, R_1 - 1)\}$）。
   - 繁殖封包發送後，具備高頻伺服端握手比對（扣心、冷卻、次數扣除），嚴格杜絕重複發送或死循環。
   - 提供「⚡ 執行單次繁殖」與「▶ 啟動全自動智能繁殖」兩種靈活操作模式。

---

## 🛠️ 系統需求與相依套件

* **作業系統**：Windows 10 / 11 (x64)
* **Python 版本**：Python 3.10+
* **相依套件**：
  ```bash
  pip install -r requirements.txt
  ```

---

## 🚀 啟動方式

1. **整合至 AI Tool Launcher**：
   * 雙擊執行目錄下的 `linkme.bat`，即可一鍵將本工具註冊至啟動器大廳。
2. **獨立手動啟動**：
   * 雙擊 `啟動自動繁殖助手.bat` 或在終端執行：
     ```bash
     python main.py
     ```

---

## 📁 目錄結構

```text
cheatengine/
├── main.py                  # 啟動器標準主程式入口
├── auto_breed_gui.py        # 現代化專業 Operate GUI 介面
├── pcfish_core.py           # 核心記憶體讀取、指標注入與遠程調用引擎
├── fish_names.json          # 官方繁體中文魚名代碼庫
├── official_fish_names.json # 原始備用魚名對照表
├── requirements.txt         # 相依套件清單 (psutil, capstone)
├── PCFish_AutoBreed.CT      # Cheat Engine 記憶體表單範本
├── auto_breed.lua           # CE 內部原生自動配種 Lua 腳本
├── 啟動自動繁殖助手.bat       # 獨立批次檔啟動捷徑
├── .gitignore               # Git 版控忽略配置
└── README.md                # 專案說明文件
```
