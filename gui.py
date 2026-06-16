import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from modules.kline_data import KlineData
from modules.grid_strategy import GridStrategy
from modules.backtester import Backtester
from modules.visualization import Visualization
import threading
from datetime import datetime
import os
import subprocess
import time
import json


class ToolTip:
    """鼠标悬停提示工具类"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None

        # 绑定鼠标事件
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window:
            return
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("Segoe UI", 9), fg="#333333")
        label.pack(ipadx=4, ipady=2)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class GridTradingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("网格策略回测系统")
        self.root.geometry("720x880")
        self.root.resizable(True, True)  # 允许窗口缩放和最大化
        self.stop_requested = False  # 回测停止标志

        # ========== 加载合约规格文件 ==========
        self.contract_specs = self.load_contract_specs()

        # ========== 自定义颜色配置 ==========
        self.colors = {
            'primary': '#4A90D9',
            'primary_dark': '#2C5AA0',
            'secondary': '#667eea',
            'success': '#28A745',
            'warning': '#FFC107',
            'danger': '#DC3545',
            'bg': '#f8f9fa',
            'bg_frame': '#ffffff',
            'text': '#333333',
            'text_light': '#666666',
            'border': '#d0d0d0',
            'hover': '#E3F2FD'
        }

        # 设置窗口背景颜色
        root.configure(bg=self.colors['bg'])

        # 创建主框架（居中显示）
        self.main_frame = tk.Frame(root, bg=self.colors['bg'])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(15, 15))

        # ========== 标题区域 ==========
        title_frame = tk.Frame(self.main_frame, bg=self.colors['primary'])
        title_frame.pack(fill=tk.X)

        title_label = tk.Label(title_frame, text="📈 网格策略回测系统",
                                 bg=self.colors['primary'], fg='white',
                                 font=('Segoe UI', 22, 'bold'))
        title_label.pack(pady=12)

        subtitle_label = tk.Label(title_frame, text="Grid Trading Strategy Backtesting System",
                                  bg=self.colors['primary'], fg='#E3F2FD',
                                  font=('Segoe UI', 10))
        subtitle_label.pack(pady=(0, 12))

        # ========== Notebook 标签页（等宽标签） - 居中布局 ==========
        # 创建一个居中的容器来包裹整个标签页区域
        notebook_wrapper = tk.Frame(self.main_frame, bg=self.colors['bg'])
        notebook_wrapper.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # 配置grid使内容居中
        notebook_wrapper.columnconfigure(0, weight=1)
        notebook_wrapper.rowconfigure(0, weight=1)
        
        # 居中的笔记本容器
        notebook_container = tk.Frame(notebook_wrapper, bg=self.colors['bg'])
        notebook_container.grid(row=0, column=0, sticky="nsew")

        # 使用自定义等宽标签按钮替代Notebook默认标签
        tab_bar = tk.Frame(notebook_container, bg=self.colors['bg'])
        tab_bar.pack(fill=tk.X)

        # 标签页内容容器
        self.tab_content = tk.Frame(notebook_container, bg=self.colors['bg'])
        self.tab_content.pack(fill=tk.BOTH, expand=True)

        # 等宽标签按钮
        self.tab_buttons = {}
        tab_width = 150  # 固定宽度确保两个标签一样大
        
        # 创建一个居中的容器来放置标签按钮
        button_container = tk.Frame(tab_bar, bg=self.colors['bg'])
        button_container.pack()

        btn1 = tk.Button(button_container, text="参数配置",
                        command=lambda: self.switch_tab(0),
                        width=tab_width // 8, height=1,
                        font=('Segoe UI', 11, 'bold'),
                        bd=1, relief='solid',
                        cursor='hand2')
        btn1.pack(side=tk.LEFT, padx=(0, 5))
        self.tab_buttons[0] = btn1

        btn2 = tk.Button(button_container, text="回测日志",
                        command=lambda: self.switch_tab(1),
                        width=tab_width // 8, height=1,
                        font=('Segoe UI', 11, 'bold'),
                        bd=1, relief='solid',
                        cursor='hand2')
        btn2.pack(side=tk.LEFT)
        self.tab_buttons[1] = btn2

        # 参数配置页
        params_frame = tk.Frame(self.tab_content, bg=self.colors['bg'])
        self.create_params_panel(params_frame)

        # 回测日志页
        log_frame = tk.Frame(self.tab_content, bg=self.colors['bg'])
        self.create_log_panel(log_frame)
        
        # 在日志页面添加进度条（显示百分比）
        progress_frame = tk.Frame(log_frame, bg=self.colors['bg'])
        progress_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        self.progress_var = tk.DoubleVar()
        # 绿色进度条样式
        style = ttk.Style()
        style.configure('green.Horizontal.TProgressbar', background='#28a745', foreground='#28a745')
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, style='green.Horizontal.TProgressbar')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # 百分比标签（绿色）
        self.progress_label = tk.Label(progress_frame, text="0%", 
                                      bg=self.colors['bg'], fg='#28a745',
                                      font=('Segoe UI', 11, 'bold'), width=5)
        self.progress_label.pack(side=tk.RIGHT)

        self.tabs = [params_frame, log_frame]
        self.current_tab = 0
        self.switch_tab(0)  # 初始化显示第一个标签页

        # ========== 底部按钮区域 ==========
        bottom_frame = tk.Frame(self.main_frame, bg=self.colors['bg'])
        bottom_frame.pack(fill=tk.X, pady=(18, 8))

        # 按钮框架
        button_frame = tk.Frame(bottom_frame, bg=self.colors['bg'])
        button_frame.pack(fill=tk.X)

        self.run_button = tk.Button(button_frame, text="🚀 开始回测",
                                    command=self.run_backtest,
                                    bg=self.colors['success'], fg='white',
                                    font=('Segoe UI', 12, 'bold'),
                                    relief='raised', bd=2, padx=10, pady=6,
                                    width=14, height=1,
                                    cursor='hand2', activebackground='#218838', activeforeground='white')
        self.run_button.pack(side=tk.LEFT, padx=(0, 15))

        self.reset_button = tk.Button(button_frame, text="🔄 重置参数",
                                      command=self.reset_params,
                                      bg=self.colors['warning'], fg='white',
                                      font=('Segoe UI', 12, 'bold'),
                                      relief='raised', bd=2, padx=10, pady=6,
                                      width=14, height=1,
                                      cursor='hand2', activebackground='#E6A800', activeforeground='white')
        self.reset_button.pack(side=tk.LEFT, padx=(0, 15))

        self.quit_button = tk.Button(button_frame, text="⏹ 停止",
                                  command=self.stop_backtest,
                                  bg=self.colors['danger'], fg='white',
                                  font=('Segoe UI', 12, 'bold'),
                                  relief='raised', bd=2, padx=10, pady=6,
                                  width=14, height=1,
                                  cursor='hand2', activebackground='#C82333', activeforeground='white')
        self.quit_button.pack(side=tk.RIGHT)

    def switch_tab(self, index):
        """切换标签页"""
        # 隐藏所有页面
        for i, tab in enumerate(self.tabs):
            tab.pack_forget()

        # 显示选中的页面
        self.tabs[index].pack(fill=tk.BOTH, expand=True)
        self.current_tab = index

        # 更新标签按钮样式：选中为蓝色，未选中为白色
        for i, btn in self.tab_buttons.items():
            if i == index:
                btn.config(bg=self.colors['primary'], fg='white')
            else:
                btn.config(bg=self.colors['bg_frame'], fg=self.colors['text'])

    def create_params_panel(self, parent):
        """创建参数配置面板"""
        # 创建一个居中的容器框架
        center_container = tk.Frame(parent, bg=self.colors['bg'])
        center_container.pack(fill=tk.BOTH, expand=True)
        
        # 配置grid列权重，使中间列居中
        center_container.columnconfigure(0, weight=1)  # 左侧空白，可伸缩
        center_container.columnconfigure(1, weight=0)  # 中间内容，固定
        center_container.columnconfigure(2, weight=1)  # 右侧空白，可伸缩
        center_container.rowconfigure(0, weight=0)
        center_container.rowconfigure(1, weight=1)

        # ========== 基本参数 ==========
        basic_frame = tk.LabelFrame(center_container, text="基本参数",
                                    bg=self.colors['bg_frame'], fg=self.colors['primary_dark'],
                                    font=('Segoe UI', 12, 'bold'),
                                    bd=1, relief='solid', padx=18, pady=10)
        basic_frame.grid(row=0, column=1, sticky="n", pady=6)

        # 使用统一列配置确保所有输入框右对齐
        basic_frame.columnconfigure(0, weight=0, minsize=100)  # 标签列
        basic_frame.columnconfigure(1, weight=1)  # 输入框列，可拉伸

        # 交易品种 - 可编辑下拉框
        self.create_label_editable_combobox(basic_frame, "交易品种:", "symbol", 
                                           ["BTC", "ETH", "AMD", "QQQ", "NVDA", "XAU", "CL"], 
                                           "BTC", row=0)

        # 价格区间 - 使用统一框架确保对齐
        tk.Label(basic_frame, text="价格区间:", bg=self.colors['bg_frame'],
                  fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=1, column=0, sticky="e", pady=5, padx=(0, 10))
        price_entry_frame = tk.Frame(basic_frame, bg=self.colors['bg_frame'])
        price_entry_frame.grid(row=1, column=1, sticky="ew", pady=5)
        price_entry_frame.columnconfigure(0, weight=1)  # 左侧空白区域
        price_entry_frame.columnconfigure(1, weight=0)  # 第一个输入框
        price_entry_frame.columnconfigure(2, weight=0)  # 波浪号
        price_entry_frame.columnconfigure(3, weight=0)  # 第二个输入框
        price_entry_frame.columnconfigure(4, weight=1)  # 右侧空白区域
        
        self.lower_bound = tk.Entry(price_entry_frame, width=10, font=('Segoe UI', 11), bd=1, relief='solid')
        self.lower_bound.grid(row=0, column=1, sticky="w", padx=(0, 5))
        self.lower_bound.insert(0, "40000")
        
        # 绑定焦点离开事件，自动解析带逗号的数字
        def on_lower_focus_out(event):
            value = self.lower_bound.get().strip()
            if value:
                try:
                    clean_value = value.replace(',', '')
                    num_value = float(clean_value)
                    self.lower_bound.delete(0, tk.END)
                    if num_value == int(num_value):
                        self.lower_bound.insert(0, str(int(num_value)))
                    else:
                        self.lower_bound.insert(0, clean_value)
                except ValueError:
                    pass
        
        self.lower_bound.bind('<FocusOut>', on_lower_focus_out)
        
        tk.Label(price_entry_frame, text=" ~ ", bg=self.colors['bg_frame'],
                  fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=0, column=2)
        
        self.upper_bound = tk.Entry(price_entry_frame, width=10, font=('Segoe UI', 11), bd=1, relief='solid')
        self.upper_bound.grid(row=0, column=3, sticky="e", padx=(5, 0))
        self.upper_bound.insert(0, "80000")
        
        # 绑定焦点离开事件，自动解析带逗号的数字
        def on_upper_focus_out(event):
            value = self.upper_bound.get().strip()
            if value:
                try:
                    clean_value = value.replace(',', '')
                    num_value = float(clean_value)
                    self.upper_bound.delete(0, tk.END)
                    if num_value == int(num_value):
                        self.upper_bound.insert(0, str(int(num_value)))
                    else:
                        self.upper_bound.insert(0, clean_value)
                except ValueError:
                    pass
        
        self.upper_bound.bind('<FocusOut>', on_upper_focus_out)

        self.create_label_entry(basic_frame, "网格数量:", "grid_count", "200", row=2)
        self.create_label_combobox(basic_frame, "网格模式:", "grid_mode", ["等差", "等比"], row=3)
        self.create_label_entry(basic_frame, "杠杆倍数:", "leverage", "3", row=4)
        self.create_label_combobox(basic_frame, "交易方向:", "direction", ["多", "空"], row=5)
        self.create_label_entry(basic_frame, "总保证金(USDT):", "total_margin", "10000", row=6)
        
        # ========== 从 contract_specs.json 读取默认品种（BTC）的规格 ==========
        default_specs = self.contract_specs.get("contracts", {}).get("BTC", {})
        default_cs = default_specs.get("contract_size", None)
        default_ml = default_specs.get("min_lot", None)
        # 如果 contract_specs.json 中没有 BTC 数据，则回退硬编码默认值
        default_cs_str = "0.01"  # OKX BTC 合约规格
        default_ml_str = "0.01"  # OKX BTC 最小交易单位
        if default_cs is not None:
            default_cs_str = str(int(default_cs)) if default_cs == int(default_cs) else str(default_cs)
        if default_ml is not None:
            default_ml_str = str(int(default_ml)) if default_ml == int(default_ml) else str(default_ml)

        # 合约规格 - 可编辑下拉框
        self.create_label_editable_combobox(basic_frame, "合约规格:", "contract_size", 
                                           ["0.01", "0.1", "1", "10", "100", "1000"], 
                                           default_cs_str, row=7,
                                           tooltip="1张对应标的数量")
        
        # 最小交易单位 - 可编辑下拉框
        self.create_label_editable_combobox(basic_frame, "最小交易单位:", "min_lot_size", 
                                           ["0.01", "0.1", "1"], 
                                           default_ml_str, row=8,
                                           tooltip="最小交易张数")
        
        self.create_label_entry(basic_frame, "市价手续费(%):", "taker_fee", "0.05", row=9)
        self.create_label_entry(basic_frame, "限价手续费(%):", "maker_fee", "0.02", row=10)
        
        # ========== 时间参数（合并到基本参数中）==========
        tk.Label(basic_frame, text="起始时间:", bg=self.colors['bg_frame'],
                fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=11, column=0, sticky="e", pady=5, padx=(0, 10))
        self.start_time = tk.Entry(basic_frame, width=18, font=('Segoe UI', 11), bd=1, relief='solid')
        self.start_time.insert(0, "2026-05-12 00:00:00")
        self.start_time.grid(row=11, column=1, sticky="ew", pady=5)  # 改为 ew 使输入框填满整列
        
        tk.Label(basic_frame, text="结束时间:", bg=self.colors['bg_frame'],
                fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=12, column=0, sticky="e", pady=5, padx=(0, 10))
        self.end_time = tk.Entry(basic_frame, width=18, font=('Segoe UI', 11), bd=1, relief='solid')
        self.end_time.insert(0, "2026-06-11 23:59:00")
        self.end_time.grid(row=12, column=1, sticky="ew", pady=5)  # 改为 ew 使输入框填满整列
        
        self.create_label_entry(basic_frame, "K线周期:", "kline_period", "1m", row=13)
        
        # K线数据路径 - 使用带三个点按钮的输入框
        tk.Label(basic_frame, text="K线数据路径:", bg=self.colors['bg_frame'],
                 fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=14, column=0, sticky="e", pady=5, padx=(0, 10))
        data_path_frame = tk.Frame(basic_frame, bg=self.colors['bg_frame'])
        data_path_frame.grid(row=14, column=1, sticky="ew", pady=5)
        
        self.kline_data_path = tk.Entry(data_path_frame, font=('Segoe UI', 11), bd=1, relief='solid')
        self.kline_data_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        # 不设默认值，必须浏览填入
        
        def browse_kline_path():
            path = filedialog.askdirectory(title="选择K线数据保存目录")
            if path:
                self.kline_data_path.delete(0, tk.END)
                self.kline_data_path.insert(0, path)
        
        ttk.Button(data_path_frame, text="...", width=3, command=browse_kline_path).pack(side=tk.RIGHT, padx=0)
        
        # 回测报告路径 - 使用带三个点按钮的输入框
        tk.Label(basic_frame, text="回测报告路径:", bg=self.colors['bg_frame'],
                 fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=15, column=0, sticky="e", pady=5, padx=(0, 10))
        report_path_frame = tk.Frame(basic_frame, bg=self.colors['bg_frame'])
        report_path_frame.grid(row=15, column=1, sticky="ew", pady=5)
        
        self.report_save_path = tk.Entry(report_path_frame, font=('Segoe UI', 11), bd=1, relief='solid')
        self.report_save_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        # 不设默认值，必须浏览填入
        
        def browse_report_path():
            path = filedialog.askdirectory(title="选择回测报告保存目录")
            if path:
                self.report_save_path.delete(0, tk.END)
                self.report_save_path.insert(0, path)
        
        ttk.Button(report_path_frame, text="...", width=3, command=browse_report_path).pack(side=tk.RIGHT, padx=0)

        # ========== 绑定交易品种的选择/输入事件，自动填充合约规格 ==========
        self.symbol.bind("<<ComboboxSelected>>", self.on_symbol_change)
        self.symbol.bind("<FocusOut>", self.on_symbol_change)
        # 初始化时基于默认品种填充一次
        self.on_symbol_change(None)

    def load_contract_specs(self):
        """加载合约规格文件 contract_specs.json
        优先查找 exe/脚本所在目录（方便用户手动修改），
        找不到时再回退到 PyInstaller 临时资源目录 _MEIPASS。
        """
        candidate_dirs = []

        # 1) 脚本/exe 所在目录
        try:
            import sys as _sys
            if getattr(_sys, "frozen", False):
                candidate_dirs.append(os.path.dirname(os.path.abspath(_sys.executable)))
            else:
                candidate_dirs.append(os.path.dirname(os.path.abspath(__file__)))
        except Exception:
            pass

        # 2) PyInstaller 临时解压目录（打包后资源所在位置）
        meipass = getattr(__import__("sys"), "_MEIPASS", None)
        if meipass:
            candidate_dirs.append(meipass)

        # 3) 最后兜底：当前工作目录
        candidate_dirs.append(os.getcwd())

        for d in candidate_dirs:
            p = os.path.join(d, "contract_specs.json")
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    continue
        # 所有路径都找不到时返回空字典，不影响其他功能
        return {"contracts": {}}

    def on_symbol_change(self, event):
        """当交易品种被选择或手动输入时，自动填充合约规格和最小交易单位
        保留用户的可选（下拉框）与手动输入功能。
        """
        # 确保相关组件已经创建
        if not hasattr(self, 'symbol') or not hasattr(self, 'contract_specs'):
            return
        symbol = self.symbol.get().strip().upper()
        # 去除可能存在的 USDT / USDT_PERP 后缀，匹配 contract_specs.json 的 key
        lookup = symbol
        for suffix in ("USDT", "BUSD", "USDC", "PERP"):
            if lookup.endswith(suffix) and lookup != suffix:
                lookup = lookup[: -len(suffix)]
        lookup = lookup.strip()

        specs = self.contract_specs.get("contracts", {}) if isinstance(self.contract_specs, dict) else {}

        if lookup and lookup in specs:
            info = specs[lookup]
            contract_size_val = info.get("contract_size", 1.0)
            min_lot_val = info.get("min_lot", 0.01)
            # 格式化数值：整数就不带小数点；否则保留合理小数位
            cs_str = str(int(contract_size_val)) if contract_size_val == int(contract_size_val) else str(contract_size_val)
            ml_str = str(int(min_lot_val)) if min_lot_val == int(min_lot_val) else str(min_lot_val)
            try:
                # 填充到输入框（保留用户手动修改的能力）
                self.contract_size.set(cs_str)
                self.min_lot_size.set(ml_str)

                # 将自动填入的值也加入下拉选项列表，留作后续手动选择
                current_cs_values = list(self.contract_size['values'])
                if cs_str not in current_cs_values:
                    self.contract_size['values'] = current_cs_values + [cs_str]

                current_ml_values = list(self.min_lot_size['values'])
                if ml_str not in current_ml_values:
                    self.min_lot_size['values'] = current_ml_values + [ml_str]
            except Exception:
                pass
        # 若未找到规格，则不修改现有值，保持用户已填的值不变

    def create_log_panel(self, parent):
        """创建回测日志面板"""
        self.log_text = scrolledtext.ScrolledText(parent,
                                                 width=80,
                                                 font=('Consolas', 14),
                                                 bg='white',
                                                 fg='#2B2B2B',
                                                 insertbackground='black',
                                                 wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        self.log_text.insert(tk.INSERT, "网格策略回测系统日志\n")
        self.log_text.insert(tk.INSERT, "="*40 + "\n")
        self.log_text.insert(tk.INSERT, "请在「参数配置」页设置参数后点击「开始回测」\n\n")
        self.log_text.config(state=tk.DISABLED)

    def create_label_entry(self, parent, label_text, var_name, default_value, row):
        """创建标签和输入框"""
        tk.Label(parent, text=label_text, bg=self.colors['bg_frame'],
                fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=row, column=0, sticky="e", pady=5, padx=(0, 10))
        entry = tk.Entry(parent, width=18, font=('Segoe UI', 11), bd=1, relief='solid')
        entry.insert(0, default_value)
        entry.grid(row=row, column=1, sticky="ew", pady=5)  # 改为 ew 使输入框填满整列
        setattr(self, var_name, entry)

    def create_price_entry(self, parent, label_text, var_name, default_value, row):
        """创建带逗号解析的价格输入框"""
        tk.Label(parent, text=label_text, bg=self.colors['bg_frame'],
                fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=row, column=0, sticky="e", pady=5, padx=(0, 10))
        entry = tk.Entry(parent, width=8, font=('Segoe UI', 11), bd=1, relief='solid')
        entry.insert(0, default_value)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        
        # 绑定焦点离开事件，自动解析带逗号的数字
        def on_focus_out(event):
            value = entry.get().strip()
            if value:
                try:
                    # 移除所有逗号
                    clean_value = value.replace(',', '')
                    # 尝试转换为浮点数
                    num_value = float(clean_value)
                    # 清空并重新填入格式化后的值（保留原始格式或简化）
                    entry.delete(0, tk.END)
                    # 如果是整数，显示为整数；否则保留小数
                    if num_value == int(num_value):
                        entry.insert(0, str(int(num_value)))
                    else:
                        entry.insert(0, clean_value)
                except ValueError:
                    pass  # 如果转换失败，保持原样
        
        entry.bind('<FocusOut>', on_focus_out)
        setattr(self, var_name, entry)

    def create_label_combobox(self, parent, label_text, var_name, values, row):
        """创建标签和下拉框"""
        tk.Label(parent, text=label_text, bg=self.colors['bg_frame'],
                fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=row, column=0, sticky="e", pady=5, padx=(0, 10))
        combo = ttk.Combobox(parent, values=values, width=16, state="readonly", font=('Segoe UI', 11))
        combo.set(values[0])
        combo.grid(row=row, column=1, sticky="ew", pady=5)  # 改为 ew 使下拉框填满整列
        setattr(self, var_name, combo)

    def create_label_editable_combobox(self, parent, label_text, var_name, values, default_value, row, tooltip=None):
        """创建标签和可编辑下拉选择框（支持手动输入）"""
        tk.Label(parent, text=label_text, bg=self.colors['bg_frame'],
                fg=self.colors['text'], font=('Segoe UI', 11)).grid(row=row, column=0, sticky="e", pady=5, padx=(0, 10))
        combo = ttk.Combobox(parent, values=values, width=16, font=('Segoe UI', 11))
        combo.set(default_value)
        combo.grid(row=row, column=1, sticky="ew", pady=5)
        
        if tooltip:
            ToolTip(combo, tooltip)
        
        setattr(self, var_name, combo)

    def log(self, message):
        """向日志框添加消息（不显示时间）"""
        self.log_text.config(state=tk.NORMAL)
        # 移除时间戳，直接输出消息
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def update_progress(self, value):
        """更新进度条和百分比标签"""
        self.progress_var.set(value)
        self.progress_label.config(text=f"{int(value)}%")
        self.root.update_idletasks()

    def reset_params(self):
        """重置参数为默认值"""
        self.symbol.set("BTC")  # Combobox使用set方法
        self.lower_bound.delete(0, tk.END)
        self.lower_bound.insert(0, "40000")
        self.upper_bound.delete(0, tk.END)
        self.upper_bound.insert(0, "80000")
        self.grid_count.delete(0, tk.END)
        self.grid_count.insert(0, "200")
        self.grid_mode.set("等差")
        self.leverage.delete(0, tk.END)
        self.leverage.insert(0, "3")
        self.direction.set("多")
        self.total_margin.delete(0, tk.END)
        self.total_margin.insert(0, "10000")
        self.start_time.delete(0, tk.END)
        self.start_time.insert(0, "2026-05-12 00:00:00")
        self.end_time.delete(0, tk.END)
        self.end_time.insert(0, "2026-06-11 23:59:59")
        self.kline_period.delete(0, tk.END)
        self.kline_period.insert(0, "1m")
        # 重置时从 contract_specs.json 读取当前品种的值
        current_default_specs = self.contract_specs.get("contracts", {}).get("BTC", {})
        reset_cs_val = current_default_specs.get("contract_size", 0.01)
        reset_ml_val = current_default_specs.get("min_lot", 0.01)
        reset_cs_str = str(int(reset_cs_val)) if reset_cs_val == int(reset_cs_val) else str(reset_cs_val)
        reset_ml_str = str(int(reset_ml_val)) if reset_ml_val == int(reset_ml_val) else str(reset_ml_val)
        self.contract_size.set(reset_cs_str)
        self.min_lot_size.set(reset_ml_str)
        self.taker_fee.delete(0, tk.END)
        self.taker_fee.insert(0, "0.05")
        self.maker_fee.delete(0, tk.END)
        self.maker_fee.insert(0, "0.02")
        
        # 重置路径字段（清空，不设默认值）
        self.kline_data_path.delete(0, tk.END)
        self.report_save_path.delete(0, tk.END)

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.INSERT, "📊 网格策略回测系统日志\n")
        self.log_text.insert(tk.INSERT, "="*40 + "\n")
        self.log_text.insert(tk.INSERT, "请在「参数配置」页设置参数后点击「开始回测」\n\n")
        self.log_text.config(state=tk.DISABLED)

        self.log("🔄 参数已重置为默认值")
        # 重置后根据默认品种自动填充合约规格
        self.on_symbol_change(None)

    def run_backtest(self):
        """执行回测（使用线程避免阻塞GUI）"""
        # 首先检查路径是否填入
        kline_data_path = self.kline_data_path.get()
        report_save_path = self.report_save_path.get()
        
        if not kline_data_path or not report_save_path:
            messagebox.showerror("错误", "请选择K线数据和回测报告保存路径")
            return
        
        # 重置停止标志
        self.stop_requested = False
        
        # 禁用按钮防止重复点击
        self.run_button.config(state=tk.DISABLED, bg='#cccccc')
        
        # 切换到日志页面并清空
        self.switch_tab(1)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.INSERT, "📊 网格策略回测系统日志\n")
        self.log_text.insert(tk.INSERT, "="*40 + "\n\n")
        self.log_text.config(state=tk.DISABLED)
        self.update_progress(0)
        
        # 在后台线程中执行回测
        thread = threading.Thread(target=self._run_backtest_thread, daemon=True)
        thread.start()
    
    def _run_backtest_thread(self):
        """在线程中执行回测逻辑"""
        try:
            self.log("🔄 正在回测...")
            
            # 定义停止回调：返回 True 表示需要停止
            def stop_callback():
                return self.stop_requested
            
            args = {
                'symbol': self.symbol.get(),
                'lower_bound': float(self.lower_bound.get()),
                'upper_bound': float(self.upper_bound.get()),
                'grid_count': int(self.grid_count.get()),
                'grid_mode': self.grid_mode.get(),
                'leverage': int(self.leverage.get()),
                'direction': self.direction.get(),
                'total_margin': float(self.total_margin.get()),
                'start_time': self.start_time.get(),
                'end_time': self.end_time.get(),
                'kline_period': self.kline_period.get(),
                'contract_size': float(self.contract_size.get()),
                'min_lot_size': float(self.min_lot_size.get()),
                'taker_fee': float(self.taker_fee.get()) / 100,
                'maker_fee': float(self.maker_fee.get()) / 100
            }

            if args['lower_bound'] >= args['upper_bound']:
                messagebox.showerror("错误", "价格区间下限必须小于价格区间上限")
                self.run_button.config(state=tk.NORMAL, bg=self.colors['success'])
                return

            # 停止检查点1
            if stop_callback():
                raise InterruptedError("用户停止回测")
            
            self.update_progress(10)

            start_time = datetime.strptime(args['start_time'], '%Y-%m-%d %H:%M:%S')
            end_time = datetime.strptime(args['end_time'], '%Y-%m-%d %H:%M:%S')

            kline_data_path = self.kline_data_path.get()
            report_save_path = self.report_save_path.get()
            
            # 确保目录存在（只在有需要时创建）
            os.makedirs(kline_data_path, exist_ok=True)
            os.makedirs(report_save_path, exist_ok=True)
            
            self.log(f"正在获取 {args['symbol']} K线数据...")
            kline_data = KlineData(data_dir=kline_data_path, log_callback=self.log, stop_callback=stop_callback)
            df = kline_data.get_kline_data(args['symbol'], start_time, end_time, args['kline_period'])

            # 停止检查点2
            if stop_callback():
                raise InterruptedError("用户停止回测")

            if df.empty:
                messagebox.showerror("错误", "未获取到K线数据，回测终止")
                self.run_button.config(state=tk.NORMAL, bg=self.colors['success'])
                return

            self.log(f"✓ 获取到 {len(df)} 条K线数据")
            self.update_progress(25)

            first_time = df.iloc[0]['timestamp']
            last_time = df.iloc[-1]['timestamp']
            # K线时间戳为开盘时间，最后一根K线还覆盖一个周期
            if len(df) >= 2:
                bar_interval = df.iloc[1]['timestamp'] - df.iloc[0]['timestamp']
                actual_end = last_time + bar_interval
            else:
                actual_end = last_time + timedelta(minutes=1)

            # 显示用户请求时间范围 vs 实际回测时间范围
            data_start_str = first_time.strftime('%Y-%m-%d %H:%M:%S')
            data_end_str = actual_end.strftime('%Y-%m-%d %H:%M:%S')
            user_start_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
            user_end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

            self.log(f"用户请求时间: [{user_start_str} 至 {user_end_str}]")
            self.log(f"实际回测时间: [{data_start_str} 至 {data_end_str}]")

            if first_time > start_time or actual_end < end_time:
                self.log(f"⚠ 实际数据范围小于请求范围（可能部分数据获取失败），回测将基于实际可用数据进行")

            time_diff = actual_end - first_time
            days = time_diff.days
            hours = (time_diff.seconds % 86400) // 3600
            minutes = (time_diff.seconds % 3600) // 60
            self.log(f"实际回测时长 {days}天 {hours}小时 {minutes}分钟（{len(df)} 条K线）")

            init_price = df.iloc[0]['close']

            self.log("\n📋 初始化策略参数...")
            strategy = GridStrategy(
                upper_bound=args['upper_bound'],
                lower_bound=args['lower_bound'],
                grid_count=args['grid_count'],
                mode=args['grid_mode'],
                leverage=args['leverage'],
                direction=args['direction'],
                contract_type=args['symbol'],
                contract_size=args['contract_size'],
                min_lot_size=args['min_lot_size'],
                taker_fee=args['taker_fee'],
                maker_fee=args['maker_fee']
            )
            self.update_progress(40)

            self.log("=" * 40)
            strategy.print_strategy_params(args['total_margin'], init_price, print_func=self.log)
            self.update_progress(55)

            self.log("\n🔄 开始回测...")
            self.log("=" * 40)
            backtester = Backtester(strategy, df, args['total_margin'])
            results = backtester.run(progress_callback=self.update_progress, stop_callback=stop_callback)
            
            # 停止检查点3
            if stop_callback():
                raise InterruptedError("用户停止回测")
            
            # 回测完成后直接跳到100%
            self.update_progress(100)

            self.log("🎉 回测结果")
            backtester.print_results(results, print_func=self.log)

            start_date_str = start_time.strftime('%Y-%m-%d')
            end_date_str = end_time.strftime('%Y-%m-%d')
            file_name = f'{args["symbol"]}_{start_date_str}_{end_date_str}'

            backtester.trade_record.save_to_excel(os.path.join(report_save_path, f'{file_name}.xlsx'))
            self.log(f"\n📁 交易记录已保存到: {os.path.join(report_save_path, f'{file_name}.xlsx')}")

            visualization = Visualization(results)
            html_path = visualization.generate_html_report(args['symbol'], file_name, output_dir=report_save_path)
            self.log(f"📊 HTML报告已保存到: {os.path.join(report_save_path, f'{file_name}.html')}")

            if os.path.exists(html_path):
                time.sleep(1)
                abs_path = os.path.abspath(html_path)
                subprocess.Popen(['start', '', abs_path], shell=True, cwd=os.getcwd())
                self.log(f"🌐 已打开报告: {abs_path}")

        except InterruptedError as ie:
            # 用户主动停止回测
            self.root.after(0, lambda: self._handle_stop())
        except Exception as e:
            # 在线程中发生错误，需要在主线程中显示错误信息
            error_msg = str(e)
            self.root.after(0, lambda: self._handle_error(error_msg))
        else:
            # 回测成功完成，在主线程中更新UI
            self.root.after(0, self._backtest_complete)
    
    def _handle_error(self, error_msg):
        """在主线程中处理错误"""
        self.log(f"\n❌ 回测出错: {error_msg}")
        messagebox.showerror("错误", f"回测出错: {error_msg}")
        self.run_button.config(state=tk.NORMAL, bg=self.colors['success'])
    
    def _backtest_complete(self):
        """回测完成后的清理工作（在主线程中调用）"""
        self.update_progress(100)
        #self.log("\n")
        self.log("✅ 回测完成！报告已自动打开")
        self.run_button.config(state=tk.NORMAL, bg=self.colors['success'])

    def stop_backtest(self):
        """停止当前回测（在主线程中由停止按钮调用）"""
        if self.run_button.cget('state') != tk.DISABLED:
            # 当前没有正在进行的回测
            return
        self.stop_requested = True
        self.log("\n⏹ 用户请求停止回测...")

    def _handle_stop(self):
        """用户停止回测后的清理工作（在主线程中调用）"""
        self.log("\n" + "=" * 40)
        self.log("⏹ 回测已被用户停止")
        self.log("=" * 40)
        self.update_progress(100)
        self.run_button.config(state=tk.NORMAL, bg=self.colors['success'])


if __name__ == "__main__":
    root = tk.Tk()
    app = GridTradingGUI(root)
    root.mainloop()
