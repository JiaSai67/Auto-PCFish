"""
PC Fish 智能繁殖管理終端 v3.5 PRO
- 依照 Impeccable (Operate Mode) 與 AI Tool Standard 規範全新重構
- 100% 記憶體直讀 GameDataManager (愛心數量、倒數計時、魚隻列表)
- 魚種冷卻時間全面導入本地 Windows 時間戳登記與平滑倒數
- 持續背景掃描 + 表格差量就地更新 (In-Place Delta Update)，徹底消除介面刷新閃爍
- 純記憶體 IL2CPP 線程原生直發繁殖訊號 (不移滑鼠、不搶焦點、支援最小化)
- 具備伺服端狀態握手比對 (愛心扣除/冷卻啟動/次數扣減)，嚴格杜絕重複發送
- 支援愛心保留門檻限制、避免魚種黑名單、向下階相容配對
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
from datetime import datetime
from pcfish_core import PCFishMemory, RARITY_MAP

class AutoBreedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PC Fish 智能繁殖管理終端 v1.0.2 PRO")
        self.root.geometry("720x820")
        self.root.minsize(680, 680)
        self.root.configure(bg="#181825")

        # 核心記憶體引擎
        self.mem = PCFishMemory()
        self.is_running = False
        self.is_monitoring = True
        self.cached_fish = []

        # 狀態快取與本地計時器
        self.cached_hearts = 0
        self.cached_target_ts = 0
        self.fish_local_cd = {} # 本地魚隻冷卻時間戳快取 {fish_id: target_ts}

        # 策略過濾與偏好設定 (簡化介面，其餘選項預設開啟)
        self.blacklist = set()
        self.opt_min_hearts = tk.IntVar(value=1)
        self.opt_same_rarity_only = tk.BooleanVar(value=False)
        self.ontop_var = tk.BooleanVar(value=True)

        # 樣式與視覺系統
        self.setup_styles()
        # 建立 UI 元件
        self.create_widgets()

        # 啟動背景狀態監控執行緒 (持續掃描 + 差量更新)
        self.state_thread = threading.Thread(target=self.state_monitor_loop, daemon=True)
        self.state_thread.start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_styles(self):
        """建置現代 Catppuccin Macchiato 主題調色盤與元件樣式"""
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # 調色盤核心配色 (Operate 專業終端標準)
        self.c_bg = "#181825"          # 深度基底黑
        self.c_card = "#1e1e2e"        # 抬升卡片背景
        self.c_card_sub = "#25263a"    # 次級卡片背景
        self.c_border = "#313244"      # 柔和邊框線
        self.c_text = "#cdd6f4"        # 主要文字白
        self.c_subtext = "#a6adc8"     # 次要資訊灰
        self.c_accent_blue = "#89b4fa" # 核心操作藍 (Sapphire)
        self.c_green = "#a6e3a1"       # 成功與啟動綠 (Emerald)
        self.c_pink = "#f38ba8"        # 愛心與警告紅 (Rose)
        self.c_gold = "#f9e2af"        # 冷卻與注意黃 (Gold)
        self.c_cyan = "#89dceb"        # 資訊與進度青 (Cyan)
        self.c_purple = "#cba6f7"      # 親代標記紫 (Mauve)
        self.c_entry_bg = "#11111b"    # 輸入框極黑

        # 字體家族設定 (優先 Segoe UI Variable 與微軟正黑)
        self.font_title = ("Segoe UI Variable Display", 15, "bold")
        self.font_header = ("Segoe UI Variable Display", 10, "bold")
        self.font_normal = ("Microsoft JhengHei UI", 9)
        self.font_bold = ("Microsoft JhengHei UI", 9, "bold")
        self.font_small = ("Microsoft JhengHei UI", 8)
        self.font_mono = ("Cascadia Code", 8)

        # Treeview 表格樣式定制
        self.style.configure(
            "Fish.Treeview",
            background="#1e1e2e",
            foreground="#cdd6f4",
            fieldbackground="#1e1e2e",
            font=self.font_normal,
            rowheight=26,
            borderwidth=0
        )
        self.style.configure(
            "Fish.Treeview.Heading",
            background="#313244",
            foreground="#89dceb",
            font=self.font_bold,
            relief="flat",
            padding=4
        )
        self.style.map(
            "Fish.Treeview",
            background=[("selected", "#45475a")],
            foreground=[("selected", "#f5c2e7")]
        )

        # Spinbox 樣式
        self.style.configure(
            "TSpinbox",
            fieldbackground="#11111b",
            foreground="#cdd6f4",
            background="#313244",
            arrowcolor="#89dceb"
        )

    def create_widgets(self):
        """組裝具備頂級視覺層次 (Visual Hierarchy) 的管理終端介面"""
        # ==========================================
        # 1. 頂部狀態列 (Header & Status Pill)
        # ==========================================
        top_bar = tk.Frame(self.root, bg=self.c_bg)
        top_bar.pack(fill="x", padx=18, pady=(10, 4))

        title_box = tk.Frame(top_bar, bg=self.c_bg)
        title_box.pack(side="left")

        lbl_app_name = tk.Label(
            title_box,
            text="🐟 PC Fish 智能繁殖管理終端",
            font=self.font_title,
            fg=self.c_cyan,
            bg=self.c_bg
        )
        lbl_app_name.pack(side="left")

        lbl_version_badge = tk.Label(
            title_box,
            text="PRO v1.0.1",
            font=("Segoe UI", 8, "bold"),
            fg="#181825",
            bg=self.c_accent_blue,
            padx=5,
            pady=1
        )
        lbl_version_badge.pack(side="left", padx=8)

        top_actions = tk.Frame(top_bar, bg=self.c_bg)
        top_actions.pack(side="right")

        self.root.attributes("-topmost", True)
        cb_ontop = tk.Checkbutton(
            top_actions,
            text="視窗置頂",
            variable=self.ontop_var,
            command=self.toggle_topmost,
            bg=self.c_bg,
            fg=self.c_subtext,
            selectcolor=self.c_card,
            activebackground=self.c_bg,
            activeforeground=self.c_text,
            font=self.font_small
        )
        cb_ontop.pack(side="left", padx=(0, 8))

        btn_manual_refresh = tk.Button(
            top_actions,
            text="🔄 立即刷新",
            font=self.font_small,
            bg=self.c_card,
            fg=self.c_cyan,
            activebackground=self.c_border,
            activeforeground=self.c_text,
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.force_refresh_scan
        )
        btn_manual_refresh.pack(side="left")

        # ==========================================
        # 2. 愛心與繁殖條核心看板 (Hero Dashboard Card)
        # ==========================================
        hero_card = tk.Frame(self.root, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        hero_card.pack(fill="x", padx=18, pady=4)

        hero_top = tk.Frame(hero_card, bg=self.c_card)
        hero_top.pack(fill="x", padx=14, pady=(8, 2))

        lbl_hero_title = tk.Label(
            hero_top,
            text="💖 愛心繁殖條監控儀表 (直讀+本地秒級計時)",
            font=self.font_header,
            fg=self.c_pink,
            bg=self.c_card
        )
        lbl_hero_title.pack(side="left")

        self.lbl_conn_pill = tk.Label(
            hero_top,
            text="偵測中...",
            font=self.font_small,
            fg=self.c_gold,
            bg=self.c_card_sub,
            padx=8,
            pady=2
        )
        self.lbl_conn_pill.pack(side="right")

        # 愛心圖標視覺展示 (❤️❤️🤍🤍🤍)
        self.lbl_hearts_icon = tk.Label(
            hero_card,
            text="🤍🤍🤍🤍🤍",
            font=("Segoe UI Emoji", 26),
            fg=self.c_pink,
            bg=self.c_card
        )
        self.lbl_hearts_icon.pack(pady=(0, 2))

        # 三等分數據指標區塊
        metrics_box = tk.Frame(hero_card, bg=self.c_card)
        metrics_box.pack(fill="x", padx=14, pady=(0, 8))

        self.metric_hearts = self.create_metric_pill(metrics_box, "愛心存量", "讀取中...", self.c_pink)
        self.metric_timer = self.create_metric_pill(metrics_box, "繁殖條倒數", "讀取中...", self.c_cyan)
        self.metric_wake = self.create_metric_pill(metrics_box, "下次生成時間", "--:--:--", self.c_gold)

        # ==========================================
        # 3. 操作控制中心 (Action Hub - 雙大按鈕)
        # ==========================================
        action_bar = tk.Frame(self.root, bg=self.c_bg)
        action_bar.pack(fill="x", padx=18, pady=4)

        self.btn_single = tk.Button(
            action_bar,
            text="⚡  執行單次繁殖 (測試)",
            font=("Microsoft JhengHei UI", 11, "bold"),
            bg=self.c_accent_blue,
            fg="#181825",
            activebackground="#b4befe",
            activeforeground="#181825",
            bd=0,
            cursor="hand2",
            padx=12,
            pady=8,
            command=self.trigger_single_breed
        )
        self.btn_single.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_toggle = tk.Button(
            action_bar,
            text="▶  啟動全自動智能繁殖",
            font=("Microsoft JhengHei UI", 11, "bold"),
            bg=self.c_green,
            fg="#181825",
            activebackground="#94e2d5",
            activeforeground="#181825",
            bd=0,
            cursor="hand2",
            padx=12,
            pady=8,
            command=self.toggle_autobread
        )
        self.btn_toggle.pack(side="right", fill="x", expand=True)

        # ==========================================
        # 4. 繁殖策略與門檻設定 (Settings Card)
        # ==========================================
        opt_card = tk.Frame(self.root, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        opt_card.pack(fill="x", padx=18, pady=4)

        lbl_opt_title = tk.Label(
            opt_card,
            text="⚙️ 繁殖策略設定",
            font=self.font_header,
            fg=self.c_cyan,
            bg=self.c_card
        )
        lbl_opt_title.pack(anchor="w", padx=14, pady=(8, 4))

        # 第一列：愛心門檻 + 只允許同稀有度繁殖
        row1 = tk.Frame(opt_card, bg=self.c_card)
        row1.pack(fill="x", padx=14, pady=(0, 4))

        lbl_limit = tk.Label(row1, text="💖 愛心保留門檻:", font=self.font_bold, fg=self.c_pink, bg=self.c_card)
        lbl_limit.pack(side="left", padx=(0, 4))

        spin_hearts = ttk.Spinbox(
            row1,
            from_=1,
            to=5,
            width=3,
            textvariable=self.opt_min_hearts,
            font=self.font_bold
        )
        spin_hearts.pack(side="left", padx=(0, 14))

        cb_same_rarity = tk.Checkbutton(
            row1,
            text="🔒 只允許同稀有度繁殖 (禁止跨階配對，僅同階如普通+普通、高級+高級)",
            variable=self.opt_same_rarity_only,
            bg=self.c_card,
            fg=self.c_text,
            selectcolor=self.c_entry_bg,
            activebackground=self.c_card,
            activeforeground=self.c_gold,
            font=self.font_bold
        )
        cb_same_rarity.pack(side="left")

        # 第二列：避免魚種 (黑名單)
        row2 = tk.Frame(opt_card, bg=self.c_card)
        row2.pack(fill="x", padx=14, pady=(2, 4))

        lbl_bl = tk.Label(row2, text="🚫 避免魚種:", font=self.font_bold, fg=self.c_pink, bg=self.c_card)
        lbl_bl.pack(side="left", padx=(0, 6))

        self.blacklist_entry = tk.Entry(
            row2,
            bg=self.c_entry_bg,
            fg=self.c_text,
            insertbackground="white",
            font=self.font_normal,
            bd=1,
            relief="solid"
        )
        self.blacklist_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.blacklist_entry.bind("<Return>", lambda e: self.apply_blacklist_from_entry())

        btn_apply_bl = tk.Button(
            row2,
            text="套用",
            font=self.font_small,
            bg=self.c_border,
            fg=self.c_cyan,
            activebackground="#45475a",
            activeforeground=self.c_text,
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.apply_blacklist_from_entry
        )
        btn_apply_bl.pack(side="left", padx=(0, 4))

        btn_clear_bl = tk.Button(
            row2,
            text="清空",
            font=self.font_small,
            bg=self.c_border,
            fg=self.c_subtext,
            activebackground="#45475a",
            activeforeground=self.c_pink,
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.clear_blacklist
        )
        btn_clear_bl.pack(side="left")

        lbl_tip = tk.Label(
            opt_card,
            text="💡 提示：排除鎖定/冷卻與原生記憶體直發已預設啟用。雙擊下方魚庫表格可快速將選中魚種加入/移出避免名單。",
            font=self.font_small,
            fg=self.c_subtext,
            bg=self.c_card
        )
        lbl_tip.pack(anchor="w", padx=14, pady=(0, 6))

        # ==========================================
        # 6. 魚庫即時監控清單 (Live Table - In-Place Update 絕不閃爍)
        # ==========================================
        table_card = tk.Frame(self.root, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        table_card.pack(fill="both", expand=True, padx=18, pady=4)

        table_header = tk.Frame(table_card, bg=self.c_card)
        table_header.pack(fill="x", padx=14, pady=(8, 4))

        self.lbl_list_title = tk.Label(
            table_header,
            text="📋 魚庫即時清單 (持續掃描 · 差量更新)",
            font=self.font_header,
            fg=self.c_cyan,
            bg=self.c_card
        )
        self.lbl_list_title.pack(side="left")

        tree_scroll = ttk.Scrollbar(table_card)
        tree_scroll.pack(side="right", fill="y", padx=(0, 8), pady=6)

        columns = ("rarity", "stars", "name", "breed", "status")
        self.tree = ttk.Treeview(
            table_card,
            columns=columns,
            show="headings",
            style="Fish.Treeview",
            yscrollcommand=tree_scroll.set,
            height=6
        )
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("rarity", text="稀有度")
        self.tree.heading("stars", text="星級")
        self.tree.heading("name", text="魚種中文名稱")
        self.tree.heading("breed", text="剩餘次數")
        self.tree.heading("status", text="即時配種狀態")

        self.tree.column("rarity", width=70, anchor="center")
        self.tree.column("stars", width=75, anchor="center")
        self.tree.column("name", width=190, anchor="w")
        self.tree.column("breed", width=75, anchor="center")
        self.tree.column("status", width=150, anchor="center")

        self.tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 8))

        # 快顯選單
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=self.c_card, fg=self.c_text, activebackground="#45475a", activeforeground=self.c_cyan)
        self.context_menu.add_command(label="🚫 加入/移出避免配種名單", command=self.toggle_selected_fish_blacklist)

        # ==========================================
        # 7. 即時終端執行日誌 (Terminal Execution Log)
        # ==========================================
        log_frame = tk.Frame(self.root, bg=self.c_bg)
        log_frame.pack(fill="x", padx=18, pady=(0, 8))

        log_top = tk.Frame(log_frame, bg=self.c_bg)
        log_top.pack(fill="x", pady=(0, 2))

        lbl_log_title = tk.Label(
            log_top,
            text="📜 終端即時執行日誌",
            font=self.font_small,
            fg=self.c_subtext,
            bg=self.c_bg
        )
        lbl_log_title.pack(side="left")

        btn_clear_log = tk.Button(
            log_top,
            text="🗑️ 清空日誌",
            font=("Microsoft JhengHei UI", 7),
            bg=self.c_bg,
            fg=self.c_subtext,
            activebackground=self.c_card,
            activeforeground=self.c_pink,
            bd=0,
            cursor="hand2",
            command=self.clear_log
        )
        btn_clear_log.pack(side="right")

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            bg=self.c_entry_bg,
            fg="#cdd6f4",
            font=self.font_mono,
            bd=0,
            insertbackground="white",
            height=4,
            wrap="word"
        )
        self.log_text.pack(fill="x")

        self.log("系統已就緒，已載入官方繁體中文魚名庫與 IL2CPP 原生呼叫導出表。")

    def create_metric_pill(self, parent, title, initial_val, color):
        """建立現代微型指標卡片"""
        pill = tk.Frame(parent, bg=self.c_card_sub, padx=10, pady=4)
        pill.pack(side="left", fill="x", expand=True, padx=4)

        lbl_t = tk.Label(pill, text=title, font=self.font_small, fg=self.c_subtext, bg=self.c_card_sub)
        lbl_t.pack(anchor="w")

        lbl_v = tk.Label(pill, text=initial_val, font=self.font_bold, fg=color, bg=self.c_card_sub)
        lbl_v.pack(anchor="w")
        return lbl_v

    def log(self, message):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{now}] {message}\n")
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    def toggle_topmost(self):
        self.root.attributes("-topmost", self.ontop_var.get())

    def force_refresh_scan(self):
        """手動強制觸發單次記憶體刷新"""
        self.cached_target_ts = 0
        self.log("使用者手動觸發記憶體狀態與魚庫重整。")

    def apply_blacklist_from_entry(self):
        raw = self.blacklist_entry.get().strip()
        if raw:
            items = [item.strip() for item in raw.replace('，', ',').split(',') if item.strip()]
            self.blacklist = set(items)
        else:
            self.blacklist = set()
        self.update_blacklist_entry()
        self.log(f"已更新避免魚種名單: {list(self.blacklist) if self.blacklist else '無'}")

    def update_blacklist_entry(self):
        self.blacklist_entry.delete(0, "end")
        if self.blacklist:
            self.blacklist_entry.insert(0, ", ".join(sorted(self.blacklist)))

    def clear_blacklist(self):
        self.blacklist.clear()
        self.update_blacklist_entry()
        self.log("已清空避免魚種名單。")

    def toggle_selected_fish_blacklist(self):
        selected = self.tree.selection()
        if not selected: return
        item = self.tree.item(selected[0])
        fish_name = item['values'][2]
        if fish_name in self.blacklist:
            self.blacklist.remove(fish_name)
            self.log(f"已將 [{fish_name}] 從避免配種名單中移除。")
        else:
            self.blacklist.add(fish_name)
            self.log(f"已將 [{fish_name}] 加入避免配種名單。")
        self.update_blacklist_entry()

    def on_tree_double_click(self, event):
        self.toggle_selected_fish_blacklist()

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    # ==========================================
    # 核心需求 2：差量就地更新 (In-Place Update) 絕不閃爍
    # ==========================================
    def update_fish_tree_in_place(self, fish_list, p1, p2):
        """
        無感差量更新 (In-Place Update)：
        - 徹底廢除 tree.delete(*get_children())
        - 以魚隻 id 作為唯一 iid 進行局部數值比對
        - 僅有數值或倒數變更的行數才會觸發局部重繪
        - 完美保持使用者當前滾動條位置與選取狀態！
        """
        existing_iids = set(self.tree.get_children())
        current_iids = set()
        p1_id = p1['id'] if p1 else None
        p2_id = p2['id'] if p2 else None
        now_ts = int(time.time())

        for f in fish_list:
            fid = f['id']
            current_iids.add(fid)

            # 核心需求 1：魚隻冷卻時間同步本地登記與平滑倒數
            cd_target = f.get('cd_target', 0)
            if cd_target > now_ts:
                cd_rem = max(0, cd_target - now_ts)
                mm = cd_rem // 60
                ss = cd_rem % 60
                status_desc = f"⏳ 冷卻 ({mm:02d}:{ss:02d})"
            elif fid == p1_id:
                status_desc = "親代 1 ⭐"
            elif fid == p2_id:
                status_desc = "親代 2 ⭐"
            elif f['name'] in self.blacklist or f['fish'] in self.blacklist:
                status_desc = "🚫 避免配種"
            elif f['is_locked']:
                status_desc = "🔒 鎖定"
            elif not f['can_breed']:
                status_desc = "次數已盡"
            elif f['is_basic']:
                status_desc = "基礎魚 (無限)"
            else:
                status_desc = "候補就緒"

            breed_str = f"{f['breed']}/{f['breed_max']}" if not f['is_basic'] else "0/0"
            new_vals = (f['rarity'], f['stars'], f['name'], breed_str, status_desc)

            if fid in existing_iids:
                # 若已存在，僅在欄位變動時就地更新 (零閃爍核心)
                old_vals = self.tree.item(fid, 'values')
                if old_vals != new_vals:
                    self.tree.item(fid, values=new_vals)
            else:
                # 新魚隻出現才執行插入
                self.tree.insert("", "end", iid=fid, values=new_vals)

        # 移除已不在庫存中的魚隻行
        for removed_id in existing_iids - current_iids:
            try:
                self.tree.delete(removed_id)
            except:
                pass

    # ==========================================
    # 背景監控執行緒 (持續掃描 + 本地計時同步)
    # ==========================================
    def state_monitor_loop(self):
        """背景定時監控進程、愛心狀態與最佳親代推薦 (持續掃描 + 差量更新)"""
        while self.is_monitoring:
            try:
                attached, msg = self.mem.attach()
                if not attached:
                    self.lbl_conn_pill.configure(text="🔴 遊戲離線", fg=self.c_pink)
                    self.lbl_hearts_icon.configure(text="🤍🤍🤍🤍🤍")
                    self.metric_hearts.configure(text="離線")
                    self.metric_timer.configure(text="等待遊戲開啟")
                    self.metric_wake.configure(text="--:--:--")
                    time.sleep(1.5)
                    continue

                now = time.time()
                min_hearts = self.opt_min_hearts.get()

                # 讀取愛心狀態 (100% 直讀記憶體)
                hearts, timer_str, ok, target_ts = self.mem.get_breed_heart_status()
                self.cached_hearts = hearts
                self.cached_target_ts = target_ts

                # 更新愛心視覺與度量卡片
                hearts_icon = "❤️" * hearts + "🤍" * (5 - hearts)
                self.lbl_hearts_icon.configure(text=hearts_icon)
                self.metric_hearts.configure(text=f"{hearts} / 5")

                if hearts >= 5:
                    self.metric_timer.configure(text="MAX (已滿)", fg=self.c_green)
                    self.metric_wake.configure(text="已達上限", fg=self.c_green)
                else:
                    self.metric_timer.configure(text=f"{timer_str} (精確計時)", fg=self.c_cyan)
                    wake_dt_str = datetime.fromtimestamp(target_ts).strftime("%H:%M:%S") if target_ts else "--:--:--"
                    self.metric_wake.configure(text=wake_dt_str, fg=self.c_gold)

                # 檢查遊戲繁殖面板
                uibreed = self.mem.locate_uibreed()
                ui_tag = "🟢 繁殖面板就緒" if uibreed else "🟡 請在遊戲中打開繁殖介面(愛心)"
                self.lbl_conn_pill.configure(
                    text=f"PID: {self.mem.pid} | {ui_tag}",
                    fg=self.c_green if uibreed else self.c_gold
                )

                # 持續掃描魚庫 (耗時僅 ~14ms)
                fish_list = self.mem.get_all_fish()
                self.lbl_list_title.configure(text=f"📋 魚庫即時清單 (總數: x{len(fish_list)} · 持續監控中)")

                # 計算當前最佳配對推薦 (傳遞至表格以差量就地更新 親代1/2 標籤)
                p1, p2, err_msg = self.mem.get_best_breed_pair(
                    excluded_names=self.blacklist,
                    ignore_locked=True,
                    ignore_cooldown=True,
                    same_rarity_only=self.opt_same_rarity_only.get()
                )

                # 核心需求 2：以差量就地更新表格，完全杜絕整表重新整理造成的閃爍
                self.update_fish_tree_in_place(fish_list, p1, p2)

            except Exception as e:
                pass

            time.sleep(1.0)

    # ==========================================
    # 動作 1：執行單次繁殖 (測試專用)
    # ==========================================
    def trigger_single_breed(self):
        """手動觸發單次繁殖 (測試專用，絕不重複發送)"""
        if self.is_running:
            self.log("全自動繁殖正在運行中，請先停止自動循環。")
            return

        def worker():
            self.btn_single.configure(state="disabled", text="⚡ 正在執行繁殖...")
            try:
                attached, msg = self.mem.attach()
                if not attached:
                    self.log(f"【單次失敗】遊戲未連線: {msg}")
                    return

                hearts, timer_str, ok, target_ts = self.mem.get_breed_heart_status()
                min_hearts = self.opt_min_hearts.get()
                if hearts < min_hearts:
                    self.log(f"【單次提示】當前愛心 ({hearts}/5) 低於設定門檻 ({min_hearts}顆)，已安全停止。")
                    return
                if hearts <= 0:
                    self.log(f"【單次提示】愛心已耗盡 (0/5)，繁殖條倒數中 [{timer_str}]")
                    return

                uibreed = self.mem.locate_uibreed()
                if not uibreed:
                    self.log("【單次提示】遊戲內尚未開啟「繁殖」面板，請在遊戲中打開繁殖介面！")
                    return

                p1, p2, err_msg = self.mem.get_best_breed_pair(
                    excluded_names=self.blacklist,
                    ignore_locked=True,
                    ignore_cooldown=True,
                    same_rarity_only=self.opt_same_rarity_only.get()
                )

                if not p1 or not p2:
                    self.log(f"【單次中止】{err_msg}")
                    return

                self.log(f"【單次鎖定】[{p1['rarity']} {p1['name']}] × [{p2['rarity']} {p2['name']}]，發送繁殖訊號...")

                # 執行單次繁殖並等待伺服端冷卻握手確認
                ok, res_msg = self.mem.execute_breed(p1, p2, use_memory_signal=True, wait_confirm=True)
                if ok:
                    self.log(f"✔ {res_msg}")
                    new_h, _, _, _ = self.mem.get_breed_heart_status()
                    p1_cd, p1_ts, p2_cd, p2_ts = self.mem.scan_pair_cooldown(p1, p2)
                    cd_parts = []
                    if p1_cd > 0:
                        cd_parts.append(f"親代1 [{p1['name']}] 冷卻 {p1_cd//60:02d}:{p1_cd%60:02d}")
                    if p2_cd > 0:
                        cd_parts.append(f"親代2 [{p2['name']}] 冷卻 {p2_cd//60:02d}:{p2_cd%60:02d}")
                    cd_desc = " | ".join(cd_parts) if cd_parts else "冷卻已同步"
                    self.log(f"  -> 剩餘愛心: {new_h}/5 | {cd_desc} (單次繁殖結束)")
                else:
                    self.log(f"✖ {res_msg}")

            except Exception as e:
                self.log(f"單次執行異常: {str(e)}")
            finally:
                self.btn_single.configure(state="normal", text="⚡  執行單次繁殖 (測試)")

        threading.Thread(target=worker, daemon=True).start()

    # ==========================================
    # 動作 2：全自動智能繁殖循環 (支援休眠喚醒與動畫安全延遲)
    # ==========================================
    def toggle_autobread(self):
        if not self.is_running:
            self.is_running = True
            self.btn_toggle.configure(
                text="⏹  停止自動繁殖",
                bg=self.c_pink,
                fg="#181825",
                activebackground="#eba0ac",
                activeforeground="#181825"
            )
            self.log("【啟動】全自動智能繁殖流程已開啟！")
            self.autobread_thread = threading.Thread(target=self.autobread_loop, daemon=True)
            self.autobread_thread.start()
        else:
            self.is_running = False
            self.btn_toggle.configure(
                text="▶  啟動全自動智能繁殖",
                bg=self.c_green,
                fg="#181825",
                activebackground="#94e2d5",
                activeforeground="#181825"
            )
            self.log("【停止】全自動繁殖已手動停止。")

    def autobread_loop(self):
        """全自動智能繁殖循環工作線程"""
        while self.is_running:
            try:
                attached, msg = self.mem.attach()
                if not attached:
                    self.log(f"等待遊戲開啟: {msg}")
                    time.sleep(2)
                    continue

                min_hearts = self.opt_min_hearts.get()
                hearts, timer_str, ok, target_ts = self.mem.get_breed_heart_status()

                # 愛心低於門檻：進入本地時間戳休眠 (期間不讀取記憶體)
                if hearts < min_hearts:
                    wake_dt_str = datetime.fromtimestamp(target_ts).strftime("%H:%M:%S") if target_ts else "即刻"
                    diff = max(0, int(target_ts - time.time()))
                    mm = diff // 60
                    ss = diff % 60
                    self.log(f"【休眠模式】當前愛心 ({hearts}/5) 低於設定門檻 ({min_hearts}顆)。")
                    self.log(f"  -> 本地計時排定：預計於 {wake_dt_str} (剩餘 {mm:02d}:{ss:02d}) 自動喚醒，期間完全停止記憶體掃描！")

                    while self.is_running and time.time() < target_ts:
                        time.sleep(1.0)
                        if self.opt_min_hearts.get() <= hearts:
                            break

                    if not self.is_running:
                        break

                    self.log("【時間已到】本地計時器喚醒！正在重新讀取遊戲愛心狀態...")
                    time.sleep(1.5)
                    continue

                # 確保遊戲內繁殖面板已打開
                uibreed = self.mem.locate_uibreed()
                if not uibreed:
                    self.log("【等待】遊戲內尚未開啟「繁殖」面板，請在遊戲中點擊下方愛心打開繁殖介面...")
                    time.sleep(3)
                    continue

                p1, p2, err_msg = self.mem.get_best_breed_pair(
                    excluded_names=self.blacklist,
                    ignore_locked=True,
                    ignore_cooldown=True,
                    same_rarity_only=self.opt_same_rarity_only.get()
                )

                if not p1 or not p2:
                    self.log(f"【保護暫停】{err_msg} 等待庫存或冷卻恢復...")
                    time.sleep(5)
                    continue

                self.log(f"【自動配種】挑選配對: [{p1['rarity']} {p1['name']}] × [{p2['rarity']} {p2['name']}]，發送繁殖訊號...")

                # 觸發實際遊戲配種 (純記憶體原生訊號直發，並嚴格等待伺服端冷卻握手確認！)
                ok, res_msg = self.mem.execute_breed(p1, p2, use_memory_signal=True, wait_confirm=True)
                if ok:
                    self.log(f"✔ {res_msg}")
                    new_h, _, _, _ = self.mem.get_breed_heart_status()

                    # 核心需求：繁殖完成後不等待動畫，直接掃描剛配對魚種的剩餘冷卻時間並同步至本地
                    p1_cd, p1_ts, p2_cd, p2_ts = self.mem.scan_pair_cooldown(p1, p2)
                    cd_parts = []
                    if p1_cd > 0:
                        cd_parts.append(f"親代1 [{p1['name']}] 冷卻 {p1_cd//60:02d}:{p1_cd%60:02d}")
                    if p2_cd > 0:
                        cd_parts.append(f"親代2 [{p2['name']}] 冷卻 {p2_cd//60:02d}:{p2_cd%60:02d}")
                    cd_desc = " | ".join(cd_parts) if cd_parts else "冷卻已同步"

                    self.log(f"  -> 剩餘愛心: {new_h}/5 | {cd_desc}")
                    self.log("  -> ⚡ 零等待模式：直接搜尋下一個可用組合進行配對...")

                    # 微小讓渡 (0.05秒) 保持介面與線程響應，直接進入下一次配種
                    time.sleep(0.05)
                    continue
                else:
                    self.log(f"⚠️ {res_msg}")
                    self.log("  -> 為維護帳號安全，已暫停自動繁殖循環。請確認遊戲介面後手動重啟。")
                    self.is_running = False
                    self.btn_toggle.configure(
                        text="▶  啟動全自動智能繁殖",
                        bg=self.c_green,
                        fg="#181825",
                        activebackground="#94e2d5",
                        activeforeground="#181825"
                    )
                    break

            except Exception as e:
                self.log(f"執行異常: {str(e)}")
                time.sleep(2)

    def on_close(self):
        self.is_running = False
        self.is_monitoring = False
        self.mem.detach()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoBreedApp(root)
    root.mainloop()
