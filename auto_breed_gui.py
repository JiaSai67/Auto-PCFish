"""
PC Fish 智能繁殖與合成管理終端 v1.0.9 STABLE
- 依照 Impeccable (Operate Mode) 與 AI Tool Standard 規範全新重構
- 100% 記憶體直讀 GameDataManager (愛心數量、倒數計時、魚隻列表)
- 魚種冷卻時間全面導入本地 Windows 時間戳登記與平滑倒數
- 持續背景掃描 + 表格差量就地更新 (In-Place Delta Update)，徹底消除介面刷新閃爍
- 魚單即時清單過濾次數已盡魚隻，僅展示尚有配種次數之有效魚隻與無限基礎魚
- 純記憶體 IL2CPP 線程原生直發繁殖訊號 (動態解析 Breed 方法，杜絕寫死索引閃退)
- 具備伺服端狀態握手比對 (愛心扣除/冷卻啟動/次數扣減)，嚴格杜絕重複發送
- 嚴格導入官方數值底層最高期望值黃金階梯配對 (杜絕 3+2、2+1 降階污染)
- 🌟 全新支援官方賽季魚 (FS00033 霜藍翻車魚、FS00034 萊姆背海龜、FS00035 祭典章魚) 1~5 星合成雷達
- 🌟 賽季材料自動鎖定保護 (防挪用) + 非賽季/溢出魚分流一般魚融合池 (0次廢魚優先耗損)
- 🌟 純記憶體原生直發合成/融合訊號 (直調 MergeInit + Merge，徹底杜絕彈窗與介面卡死)
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

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
from datetime import datetime
from pcfish_core import PCFishMemory, RARITY_MAP, SEASON_TARGETS, SEASON_RECIPES

class AutoBreedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PC Fish 智能繁殖與合成管理終端 v1.1.1 STABLE (純記憶體直發)")
        self.root.geometry("740x860")
        self.root.minsize(700, 720)
        self.root.configure(bg="#181825")

        # 核心記憶體引擎
        self.mem = PCFishMemory()
        self.is_running = False
        self.is_monitoring = True
        self.is_batch_merging = False
        self.stop_event = threading.Event()
        self.autobread_thread = None
        self.cached_fish = []
        self.cached_class_res = {}

        # 狀態快取與本地計時器
        self.cached_hearts = 0
        self.cached_target_ts = 0
        self.fish_local_cd = {} # 本地魚隻冷卻時間戳快取 {fish_id: target_ts}

        # 策略過濾與偏好設定
        self.blacklist = set()
        self.opt_min_hearts = tk.IntVar(value=1)
        self.opt_same_rarity_only = tk.BooleanVar(value=False)
        self.opt_max_merge_rarity = tk.IntVar(value=2) # 預設融合素材上限：高級(2)，防禦神話/傳說
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

        # 字體家族設定
        self.font_title = ("Segoe UI Variable Display", 15, "bold")
        self.font_header = ("Segoe UI Variable Display", 10, "bold")
        self.font_normal = ("Microsoft JhengHei UI", 9)
        self.font_bold = ("Microsoft JhengHei UI", 9, "bold")
        self.font_small = ("Microsoft JhengHei UI", 8)
        self.font_mono = ("Cascadia Code", 8)

        # Notebook 樣式
        self.style.configure("TNotebook", background=self.c_bg, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background=self.c_card,
            foreground=self.c_subtext,
            font=self.font_bold,
            padding=[16, 6]
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.c_card_sub)],
            foreground=[("selected", self.c_cyan)]
        )

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
            text="🐟 PC Fish 智能繁殖與合成管理終端",
            font=self.font_title,
            fg=self.c_cyan,
            bg=self.c_bg
        )
        lbl_app_name.pack(side="left")

        lbl_version_badge = tk.Label(
            title_box,
            text="v1.0.7 STABLE",
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
        # 2. Notebook 分頁系統 (繁殖中心 / 賽季合成與一般融合)
        # ==========================================
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(4, 4))

        self.tab_breed = tk.Frame(self.notebook, bg=self.c_bg)
        self.tab_season_merge = tk.Frame(self.notebook, bg=self.c_bg)

        self.notebook.add(self.tab_breed, text="  🐟 智能繁殖中心  ")
        self.notebook.add(self.tab_season_merge, text="  🌟 賽季合成雷達與一般魚融合  ")

        # 建構分頁內容
        self.create_breed_tab_widgets(self.tab_breed)
        self.create_season_merge_tab_widgets(self.tab_season_merge)

        # ==========================================
        # 3. 底部即時終端執行日誌 (Terminal Execution Log - 全分頁共享)
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

        self.log("系統已就緒，已載入官方繁體中文魚名庫、賽季合成配方庫與 IL2CPP 核心呼叫表。")

    def create_breed_tab_widgets(self, parent):
        """建構 Tab 1: 智能繁殖中心 (保持原版頂級階梯配對與無閃爍監控)"""
        # 1. 愛心與繁殖條核心看板 (Hero Dashboard Card)
        hero_card = tk.Frame(parent, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        hero_card.pack(fill="x", pady=(4, 4))

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
            font=("Segoe UI Emoji", 24),
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

        # 2. 操作控制中心 (Action Hub - 雙大按鈕)
        action_bar = tk.Frame(parent, bg=self.c_bg)
        action_bar.pack(fill="x", pady=4)

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

        # 3. 繁殖策略與門檻設定 (Settings Card)
        opt_card = tk.Frame(parent, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        opt_card.pack(fill="x", pady=4)

        lbl_opt_title = tk.Label(
            opt_card,
            text="⚙️ 繁殖策略設定",
            font=self.font_header,
            fg=self.c_cyan,
            bg=self.c_card
        )
        lbl_opt_title.pack(anchor="w", padx=14, pady=(6, 4))

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
            text="💡 提示：排除鎖定/冷卻與原生記憶體直發已預設啟用。配對優先依稀有度，次依剩餘次數少者優先耗損配種次數。",
            font=self.font_small,
            fg=self.c_subtext,
            bg=self.c_card
        )
        lbl_tip.pack(anchor="w", padx=14, pady=(0, 6))

        # 4. 魚庫即時監控清單 (Live Table - In-Place Update 絕不閃爍)
        table_card = tk.Frame(parent, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        table_card.pack(fill="both", expand=True, pady=4)

        table_header = tk.Frame(table_card, bg=self.c_card)
        table_header.pack(fill="x", padx=14, pady=(6, 4))

        self.lbl_list_title = tk.Label(
            table_header,
            text="📋 魚庫即時清單 (持續掃描 · 差量更新)",
            font=self.font_header,
            fg=self.c_cyan,
            bg=self.c_card
        )
        self.lbl_list_title.pack(side="left")

        tree_scroll = ttk.Scrollbar(table_card)
        tree_scroll.pack(side="right", fill="y", padx=(0, 8), pady=4)

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

        self.tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 6))

        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=self.c_card, fg=self.c_text, activebackground="#45475a", activeforeground=self.c_cyan)
        self.context_menu.add_command(label="🚫 加入/移出避免配種名單", command=self.toggle_selected_fish_blacklist)

    def create_season_merge_tab_widgets(self, parent):
        """建構 Tab 2: 官方賽季魚合成雷達與非賽季魚融合分流區"""
        # 1. 頂部四等分度量指標卡 (Metrics Overview)
        hero_card2 = tk.Frame(parent, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        hero_card2.pack(fill="x", pady=(4, 4))

        metrics_box2 = tk.Frame(hero_card2, bg=self.c_card)
        metrics_box2.pack(fill="x", padx=10, pady=8)

        self.metric_m_total = self.create_metric_pill(metrics_box2, "庫存總數", "讀取中...", self.c_text)
        self.metric_m_reserved = self.create_metric_pill(metrics_box2, "🛡️ 賽季保留保護", "0 條", self.c_purple)
        self.metric_m_general = self.create_metric_pill(metrics_box2, "♻️ 一般可融合池", "0 條", self.c_cyan)
        self.metric_m_ready = self.create_metric_pill(metrics_box2, "⭐ 齊全可合成", "0 組", self.c_green)

        # 2. 官方賽季魚合成雷達 (Season Craft Radar)
        radar_card = tk.Frame(parent, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        radar_card.pack(fill="both", expand=True, pady=4)

        radar_header = tk.Frame(radar_card, bg=self.c_card)
        radar_header.pack(fill="x", padx=14, pady=(6, 4))

        lbl_radar_title = tk.Label(
            radar_header,
            text="🎯 官方賽季魚合成雷達 (霜藍翻車魚 · 萊姆背海龜 · 祭典章魚 1~5星全層級)",
            font=self.font_header,
            fg=self.c_gold,
            bg=self.c_card
        )
        lbl_radar_title.pack(side="left")

        # 雷達表格
        r_scroll = ttk.Scrollbar(radar_card)
        r_scroll.pack(side="right", fill="y", padx=(0, 8), pady=4)

        r_cols = ("target", "star", "rarity", "progress", "status", "missing")
        self.tree_season = ttk.Treeview(
            radar_card,
            columns=r_cols,
            show="headings",
            style="Fish.Treeview",
            yscrollcommand=r_scroll.set,
            height=6
        )
        r_scroll.config(command=self.tree_season.yview)

        self.tree_season.heading("target", text="目標賽季魚")
        self.tree_season.heading("star", text="星級")
        self.tree_season.heading("rarity", text="稀有度")
        self.tree_season.heading("progress", text="材料進度")
        self.tree_season.heading("status", text="合成狀態")
        self.tree_season.heading("missing", text="材料狀況與缺口明細")

        self.tree_season.column("target", width=120, anchor="w")
        self.tree_season.column("star", width=55, anchor="center")
        self.tree_season.column("rarity", width=65, anchor="center")
        self.tree_season.column("progress", width=75, anchor="center")
        self.tree_season.column("status", width=95, anchor="center")
        self.tree_season.column("missing", width=250, anchor="w")

        self.tree_season.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 6))

        # 賽季合成按鈕
        radar_btn_box = tk.Frame(radar_card, bg=self.c_card)
        radar_btn_box.pack(fill="x", padx=14, pady=(0, 8))

        self.btn_season_craft = tk.Button(
            radar_btn_box,
            text="⚡  執行選定賽季魚合成 (純記憶體發送)",
            font=("Microsoft JhengHei UI", 10, "bold"),
            bg=self.c_accent_blue,
            fg="#181825",
            activebackground="#b4befe",
            activeforeground="#181825",
            bd=0,
            cursor="hand2",
            padx=12,
            pady=6,
            command=self.trigger_season_craft
        )
        self.btn_season_craft.pack(side="left", fill="x", expand=True)

        # 3. 一般魚分流池 & 快速融合 (General Merge Hub)
        general_card = tk.Frame(parent, bg=self.c_card, highlightthickness=1, highlightbackground=self.c_border)
        general_card.pack(fill="x", pady=(4, 4))

        gen_header = tk.Frame(general_card, bg=self.c_card)
        gen_header.pack(fill="x", padx=14, pady=(6, 2))

        lbl_gen_title = tk.Label(
            gen_header,
            text="♻️ 非賽季魚分流池 & 一般融合 (0次繁殖廢魚優先耗損)",
            font=self.font_header,
            fg=self.c_cyan,
            bg=self.c_card
        )
        lbl_gen_title.pack(side="left")

        lbl_gen_safety = tk.Label(
            general_card,
            text="🛡️ 安全隔離防禦已生效：已自動鎖定保護所有賽季材料魚，並嚴格杜絕神話與傳說魚隻，僅以普通/高級多餘廢魚提純星級。",
            font=self.font_small,
            fg=self.c_subtext,
            bg=self.c_card
        )
        lbl_gen_safety.pack(anchor="w", padx=14, pady=(0, 4))

        # 當前候選 10 隻預覽
        self.lbl_batch_preview = tk.Label(
            general_card,
            text="候選融合批次: 正在讀取庫存...",
            font=self.font_bold,
            fg=self.c_text,
            bg=self.c_card_sub,
            padx=10,
            pady=6,
            anchor="w",
            justify="left"
        )
        self.lbl_batch_preview.pack(fill="x", padx=14, pady=(0, 6))

        # 雙按鈕：執行單次融合 / 連續批量融合
        gen_action_box = tk.Frame(general_card, bg=self.c_card)
        gen_action_box.pack(fill="x", padx=14, pady=(0, 8))

        self.btn_single_merge = tk.Button(
            gen_action_box,
            text="⚡  執行單次一般魚融合 (10隻)",
            font=("Microsoft JhengHei UI", 10, "bold"),
            bg=self.c_cyan,
            fg="#181825",
            activebackground="#a6e3a1",
            activeforeground="#181825",
            bd=0,
            cursor="hand2",
            padx=12,
            pady=6,
            command=self.trigger_single_merge
        )
        self.btn_single_merge.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_batch_merge = tk.Button(
            gen_action_box,
            text="▶  連續自動融合 (融完所有 0次廢魚)",
            font=("Microsoft JhengHei UI", 10, "bold"),
            bg=self.c_green,
            fg="#181825",
            activebackground="#94e2d5",
            activeforeground="#181825",
            bd=0,
            cursor="hand2",
            padx=12,
            pady=6,
            command=self.toggle_batch_merge
        )
        self.btn_batch_merge.pack(side="right", fill="x", expand=True)

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
        text = f"[{now}] {message}\n"
        def _append():
            try:
                self.log_text.insert("end", text)
                self.log_text.see("end")
            except:
                pass
        try:
            self.root.after(0, _append)
        except:
            pass

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
            self.log(f"已將 [{fish_name}] 從避免名單移除")
        else:
            self.blacklist.add(fish_name)
            self.log(f"已將 [{fish_name}] 加入避免名單")
        self.update_blacklist_entry()

    def on_tree_double_click(self, event):
        self.toggle_selected_fish_blacklist()

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def update_fish_tree_in_place(self, fish_list, p1, p2):
        """
        以差量就地更新表格資料 (In-Place Delta Update)：
        徹底消除整表重建 (clear & re-insert) 造成的介面頻繁閃爍與抖動！
        """
        existing_iids = set(self.tree.get_children())
        current_iids = set()
        now_ts = int(time.time())

        p1_id = p1['id'] if p1 else None
        p2_id = p2['id'] if p2 else None

        for f in fish_list:
            # 依需求：即時清單只顯示還有次數的魚種，次數已盡的不要顯示 (基礎魚無限次予以保留)
            if not f.get('is_basic', False) and f.get('breed', 0) <= 0:
                continue

            fid = f['id']
            current_iids.add(fid)

            # 魚隻冷卻時間同步本地登記與平滑倒數
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
            elif f['is_basic']:
                status_desc = "基礎魚 (無限)"
            else:
                status_desc = "候補就緒"

            breed_str = f"{f['breed']}/{f['breed_max']}" if not f['is_basic'] else "0/0"
            new_vals = (f['rarity'], f['stars'], f['name'], breed_str, status_desc)

            if fid in existing_iids:
                old_vals = self.tree.item(fid, 'values')
                if old_vals != new_vals:
                    self.tree.item(fid, values=new_vals)
            else:
                self.tree.insert("", "end", iid=fid, values=new_vals)

        for removed_id in existing_iids - current_iids:
            try:
                self.tree.delete(removed_id)
            except:
                pass

    def update_season_merge_ui(self, class_res):
        """差量更新賽季雷達與一般魚融合介面 (無閃爍)"""
        # 1. 更新 4 大度量指標
        self.metric_m_total.configure(text=f"{class_res.get('total_fish', 0)} 條")
        self.metric_m_reserved.configure(text=f"{class_res.get('reserved_count', 0)} 條受保護")
        self.metric_m_general.configure(text=f"{class_res.get('general_pool_count', 0)} 條可用")
        ready_count = len(class_res.get('ready_crafts', []))
        self.metric_m_ready.configure(
            text=f"{ready_count} 組可合成",
            fg=self.c_green if ready_count > 0 else self.c_subtext
        )

        # 2. 差量更新賽季雷達表格 (15 個配方)
        status_list = class_res.get('season_status', [])
        for item in status_list:
            iid = f"{item['target_type']}_{item['target_star']}"
            star_str = "★" * item['target_star']
            missing_str = ", ".join(item['missing']) if item['missing'] else "材料齊全 ✨ (隨時可合成)"
            status_text = "【可合成!】" if item['is_ready'] else (f"籌備中 ({item['progress']})" if item['progress_val'] > 0 else "未開始")
            vals = (
                item['target_name'],
                star_str,
                item['target_rarity'],
                item['progress'],
                status_text,
                missing_str
            )
            if self.tree_season.exists(iid):
                if self.tree_season.item(iid, 'values') != vals:
                    self.tree_season.item(iid, values=vals)
            else:
                self.tree_season.insert("", "end", iid=iid, values=vals)

        # 3. 更新一般融合批次預覽
        batches = class_res.get('general_batches', [])
        if batches:
            b0 = batches[0]
            summary_items = [f"{f['name']}({f['breed']}次)" for f in b0[:4]]
            b_desc = f"第 1 組待融合 (共 {len(batches)} 組 / {len(batches)*10} 條)：\n  👉 " + "、".join(summary_items) + f" 等 10 隻 (優先消耗 0次或低配種廢魚)"
            self.lbl_batch_preview.configure(text=b_desc, fg=self.c_text)
            self.btn_single_merge.configure(state="normal")
        else:
            cand_cnt = class_res.get('general_pool_count', 0)
            self.lbl_batch_preview.configure(
                text=f"候選魚隻不足 10 隻 (目前 {cand_cnt}/10 條)，暫無可融合批次。",
                fg=self.c_subtext
            )
            self.btn_single_merge.configure(state="disabled")

    # ==========================================
    # 背景監控執行緒 (持續掃描 + 本地計時同步)
    # ==========================================
    def state_monitor_loop(self):
        """背景定時監控進程、愛心狀態、繁殖推薦與賽季合成進度 (持續掃描 + 差量更新)"""
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

                # 持續掃描魚庫與分類 (耗時約 20ms)
                fish_list = self.mem.get_all_fish()
                active_count = sum(1 for f in fish_list if f.get('is_basic', False) or f.get('breed', 0) > 0)
                self.lbl_list_title.configure(text=f"📋 魚庫即時清單 (可配種: x{active_count} · 總庫存: x{len(fish_list)})")

                # 計算當前最佳配對推薦
                p1, p2, err_msg = self.mem.get_best_breed_pair(
                    excluded_names=self.blacklist,
                    ignore_locked=True,
                    ignore_cooldown=True,
                    same_rarity_only=self.opt_same_rarity_only.get()
                )

                # 差量更新 Tab 1 表格
                self.update_fish_tree_in_place(fish_list, p1, p2)

                # 快速分類並差量更新 Tab 2 賽季雷達與一般魚融合
                class_res = self.mem.get_season_and_general_classification(
                    all_fish=fish_list,
                    max_merge_rarity=self.opt_max_merge_rarity.get()
                )
                self.cached_class_res = class_res
                self.update_season_merge_ui(class_res)

            except Exception as e:
                pass

            time.sleep(1.0)

    # ==========================================
    # 繁殖動作 1：執行單次繁殖 (測試專用)
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

                self.log(f"【單次鎖定】[{p1['rarity']} {p1['name']}] × [{p2['rarity']} {p2['name']}]，發送純記憶體繁殖訊號...")

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
    # 繁殖動作 2：全自動智能繁殖循環
    # ==========================================
    def toggle_autobread(self):
        if not self.is_running:
            if self.autobread_thread and self.autobread_thread.is_alive():
                self.stop_event.set()
                self.autobread_thread.join(timeout=0.5)

            self.stop_event.clear()
            self.is_running = True
            self.btn_toggle.configure(
                text="⏹  停止自動繁殖",
                bg=self.c_pink,
                fg="#181825",
                activebackground="#eba0ac",
                activeforeground="#181825"
            )
            self.log("【啟動】全自動智能繁殖流程已開啟！(100% 純記憶體訊號直發模式)")
            self.autobread_thread = threading.Thread(target=self.autobread_loop, daemon=True)
            self.autobread_thread.start()
        else:
            self.is_running = False
            self.stop_event.set()
            self.btn_toggle.configure(
                text="▶  啟動全自動智能繁殖",
                bg=self.c_green,
                fg="#181825",
                activebackground="#94e2d5",
                activeforeground="#181825"
            )
            self.log("【停止】全自動智能繁殖流程已安全停止。")

    def autobread_loop(self):
        """全自動智能繁殖後台主循環 (嚴格 Event 生命週期管理，徹底杜絕多執行緒並發洩漏)"""
        while self.is_running and not self.stop_event.is_set():
            try:
                attached, msg = self.mem.attach()
                if not attached:
                    self.log(f"【休眠】{msg}")
                    if self.stop_event.wait(3.0): break
                    continue

                hearts, timer_str, ok, target_ts = self.mem.get_breed_heart_status()
                min_hearts = self.opt_min_hearts.get()

                if hearts < min_hearts:
                    now = time.time()
                    sleep_sec = max(2.0, target_ts - now + 1.5) if (target_ts and target_ts > now) else 5.0
                    sleep_sec = min(sleep_sec, 60.0)
                    self.log(f"【休眠等待】當前愛心 ({hearts}/5) 低於設定門檻 ({min_hearts}顆)。繁殖條 [{timer_str}]，預計休眠 {sleep_sec:.0f} 秒...")
                    if self.stop_event.wait(sleep_sec): break
                    continue

                uibreed = self.mem.locate_uibreed()
                if not uibreed:
                    self.log("【等待】遊戲尚未打開「繁殖」面板，請在遊戲中打開繁殖介面...")
                    if self.stop_event.wait(2.0): break
                    continue

                p1, p2, err_msg = self.mem.get_best_breed_pair(
                    excluded_names=self.blacklist,
                    ignore_locked=True,
                    ignore_cooldown=True,
                    same_rarity_only=self.opt_same_rarity_only.get()
                )

                if not p1 or not p2:
                    self.log(f"【等待可用親代】{err_msg}。等待 3 秒重新檢查...")
                    if self.stop_event.wait(3.0): break
                    continue

                self.log(f"【智能鎖定】[{p1['rarity']} {p1['name']}] × [{p2['rarity']} {p2['name']}] (剩餘次數: {p1['breed']}/{p2['breed']})，發送繁殖訊號...")

                # 100% 純記憶體訊號直發 (v1.0.7/v1.0.8 穩定架構)
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
                    self.log(f"  -> 剩餘愛心: {new_h}/5 | {cd_desc}")

                    if self.stop_event.wait(1.8): break
                else:
                    self.log(f"✖ {res_msg}，休眠 3 秒後重試...")
                    if self.stop_event.wait(3.0): break

            except Exception as e:
                self.log(f"繁殖循環發生未預期異常: {str(e)}")
                if self.stop_event.wait(3.0): break

    # ==========================================
    # 合成動作 1：執行選中的賽季魚合成
    # ==========================================
    def trigger_season_craft(self):
        """執行選中的賽季魚合成 (100% 原生記憶體直發)"""
        selected = self.tree_season.selection()
        if not selected:
            self.log("【賽季合成】請先在上方雷達表中點選要合成的目標賽季魚！")
            return

        iid = selected[0] # e.g. "FS00035_1"
        s_type, s_star_str = iid.split('_')
        s_star = int(s_star_str)

        def worker():
            self.btn_season_craft.configure(state="disabled", text="⚡ 正在發送賽季合成訊號...")
            try:
                attached, msg = self.mem.attach()
                if not attached:
                    self.log(f"【賽季合成失敗】遊戲未連線: {msg}")
                    return

                class_res = self.mem.get_season_and_general_classification(
                    max_merge_rarity=self.opt_max_merge_rarity.get()
                )

                # 尋找是否具備齊全材料
                ready_craft = None
                for rc in class_res.get('ready_crafts', []):
                    if rc['target_type'] == s_type and rc['target_star'] == s_star:
                        ready_craft = rc
                        break

                if not ready_craft:
                    for st in class_res.get('season_status', []):
                        if st['target_type'] == s_type and st['target_star'] == s_star:
                            missing_str = ", ".join(st['missing']) if st['missing'] else "材料不足"
                            self.log(f"【賽季材料不足】{st['target_name']} {st['target_star']}星: 目前進度 {st['progress']}，缺少: {missing_str}")
                            return
                    self.log("【賽季合成提示】材料尚未滿足 10/10 需求。")
                    return

                self.log(f"【開始賽季合成】{ready_craft['target_name']} {ready_craft['target_star']}星 材料已 10/10 齊全，直發純記憶體合成訊號...")

                ok, res_msg = self.mem.execute_pure_signal_merge(
                    ready_craft['materials'],
                    merge_type=1,
                    target_season_type=s_type,
                    target_star=s_star
                )
                if ok:
                    self.log(f"🎉 賽季合成成功: {res_msg}")
                    self.force_refresh_scan()
                else:
                    self.log(f"✖ 賽季合成失敗: {res_msg}")

            except Exception as e:
                self.log(f"賽季合成異常: {str(e)}")
            finally:
                self.btn_season_craft.configure(state="normal", text="⚡  執行選定賽季魚合成 (純記憶體發送)")

        threading.Thread(target=worker, daemon=True).start()

    # ==========================================
    # 合成動作 2：執行單次一般魚融合 (10隻)
    # ==========================================
    def trigger_single_merge(self):
        """執行單次一般魚融合 (100% 原生記憶體直發)"""
        if self.is_batch_merging:
            self.log("批量連續融合正在執行中，請先停止批量循環。")
            return

        def worker():
            self.btn_single_merge.configure(state="disabled", text="⚡ 正在融合...")
            try:
                attached, msg = self.mem.attach()
                if not attached:
                    self.log(f"【融合失敗】遊戲未連線: {msg}")
                    return

                class_res = self.mem.get_season_and_general_classification(
                    max_merge_rarity=self.opt_max_merge_rarity.get()
                )
                batches = class_res.get('general_batches', [])
                if not batches:
                    self.log("【融合提示】目前沒有滿足 10 隻的一般魚候選批次 (已保護賽季魚與鎖定魚)。")
                    return

                batch_10 = batches[0]
                names_summary = ", ".join([f"{f['name']}({f['breed']}次)" for f in batch_10[:3]]) + f"... 等 10 隻"
                self.log(f"【開始融合】挑選 10 隻一般魚 [{names_summary}]，發送純記憶體融合訊號...")

                ok, res_msg = self.mem.execute_pure_signal_merge(batch_10, merge_type=0)
                if ok:
                    self.log(f"✔ {res_msg}")
                    self.force_refresh_scan()
                else:
                    self.log(f"✖ {res_msg}")

            except Exception as e:
                self.log(f"單次融合異常: {str(e)}")
            finally:
                self.btn_single_merge.configure(state="normal", text="⚡  執行單次一般魚融合 (10隻)")

        threading.Thread(target=worker, daemon=True).start()

    # ==========================================
    # 合成動作 3：連續批量一般魚融合
    # ==========================================
    def toggle_batch_merge(self):
        """啟動/停止連續批量一般魚融合"""
        if not self.is_batch_merging:
            self.is_batch_merging = True
            self.btn_batch_merge.configure(
                text="⏹  停止批量融合",
                bg=self.c_pink,
                fg="#181825"
            )
            self.log("【啟動】連續自動一般魚融合循環開啟！")
            threading.Thread(target=self.batch_merge_loop, daemon=True).start()
        else:
            self.is_batch_merging = False
            self.btn_batch_merge.configure(
                text="▶  連續自動融合 (融完所有 0次廢魚)",
                bg=self.c_green,
                fg="#181825"
            )
            self.log("【停止】連續自動一般魚融合循環已停止。")

    def batch_merge_loop(self):
        """連續融合後台循環"""
        while self.is_batch_merging:
            try:
                attached, msg = self.mem.attach()
                if not attached:
                    self.log(f"【休眠】遊戲未連線: {msg}")
                    time.sleep(3.0)
                    continue

                class_res = self.mem.get_season_and_general_classification(
                    max_merge_rarity=self.opt_max_merge_rarity.get()
                )
                batches = class_res.get('general_batches', [])
                if not batches:
                    self.log("【批量結束】已無滿足條件的一般魚批次，自動停止。")
                    self.is_batch_merging = False
                    self.root.after(0, lambda: self.btn_batch_merge.configure(
                        text="▶  連續自動融合 (融完所有 0次廢魚)",
                        bg=self.c_green,
                        fg="#181825"
                    ))
                    break

                batch_10 = batches[0]
                # 安全策略：如果整組魚的繁殖次數都大於 0，且使用者僅想融 0 次廢魚
                zero_cnt = sum(1 for f in batch_10 if f['breed'] == 0)
                names_summary = ", ".join([f"{f['name']}({f['breed']}次)" for f in batch_10[:3]]) + f"... 等 10 隻"
                self.log(f"【批量發送】第 1 組 [{names_summary}] (含 {zero_cnt} 隻 0 次廢魚)...")

                ok, res_msg = self.mem.execute_pure_signal_merge(batch_10, merge_type=0)
                if ok:
                    self.log(f"✔ {res_msg}")
                    time.sleep(1.5)
                else:
                    self.log(f"✖ {res_msg}，等待 2 秒重試...")
                    time.sleep(2.0)

            except Exception as e:
                self.log(f"批量融合循環異常: {str(e)}")
                time.sleep(2.0)

    def on_close(self):
        """安全關閉視窗與背景執行緒"""
        self.is_monitoring = False
        self.is_running = False
        self.is_batch_merging = False
        self.stop_event.set()
        self.mem.detach()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoBreedApp(root)
    root.mainloop()
