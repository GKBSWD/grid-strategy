import numpy as np

class GridStrategy:
    # 默认参数
    MAINTENANCE_RATE = 0.005  # 维持保证金率
    SAFETY_OFFSET = 0.01      # 强平价安全偏移 1%
    
    # 不同合约的默认规格
    DEFAULT_CONTRACT_CONFIG = {
        'BTC': {'contract_size': 0.01, 'min_lot_size': 0.01, 'taker_fee': 0.00075, 'maker_fee': 0.00025},
        'ETH': {'contract_size': 0.1, 'min_lot_size': 0.01, 'taker_fee': 0.00075, 'maker_fee': 0.00025},
        'SOL': {'contract_size': 1, 'min_lot_size': 0.01, 'taker_fee': 0.00075, 'maker_fee': 0.00025},
        'AVAX': {'contract_size': 1, 'min_lot_size': 0.01, 'taker_fee': 0.00075, 'maker_fee': 0.00025},
        'default': {'contract_size': 0.01, 'min_lot_size': 0.01, 'taker_fee': 0.00075, 'maker_fee': 0.00025}
    }
    
    def __init__(self, upper_bound, lower_bound, grid_count, mode='等差', leverage=5, direction='多', 
                 contract_type='BTC', contract_size=None, min_lot_size=None, taker_fee=None, maker_fee=None):
        """
        初始化网格策略
        
        :param upper_bound: 价格区间上限
        :param lower_bound: 价格区间下限
        :param grid_count: 网格数量
        :param mode: 网格模式（等差/等比）
        :param leverage: 杠杆倍数
        :param direction: 交易方向（多/空）
        :param contract_type: 合约类型（BTC/ETH/SOL/AVAX等）
        :param contract_size: 合约规格（1张等于多少标的），可选，优先于contract_type
        :param min_lot_size: 最小交易单位（张数），可选，优先于contract_type
        :param taker_fee: 市价手续费比例，可选，优先于contract_type
        :param maker_fee: 限价手续费比例，可选，优先于contract_type
        """
        self.upper_bound = upper_bound
        self.lower_bound = lower_bound
        self.grid_count = grid_count
        self.mode = mode
        self.leverage = leverage
        self.direction = direction
        self.contract_type = contract_type.upper()
        
        # 获取默认合约配置
        default_config = self.DEFAULT_CONTRACT_CONFIG.get(self.contract_type, self.DEFAULT_CONTRACT_CONFIG['default'])
        
        # 设置合约参数，允许用户自定义覆盖
        self.contract_size = contract_size if contract_size is not None else default_config['contract_size']
        self.min_lot_size = min_lot_size if min_lot_size is not None else default_config['min_lot_size']
        self.taker_fee = taker_fee if taker_fee is not None else default_config['taker_fee']
        self.maker_fee = maker_fee if maker_fee is not None else default_config['maker_fee']
        
        self.grids = []
        self.calculate_grids()
        
        # 计算安全边界（强平价必须在此边界之外）
        if self.direction == '多':
            # 多单：强平价需低于区间下限的99%
            self.liquidation_safe_price = self.lower_bound * (1 - self.SAFETY_OFFSET)
        else:
            # 空单：强平价需高于区间上限的101%
            self.liquidation_safe_price = self.upper_bound * (1 + self.SAFETY_OFFSET)
        
        # 安全参数（延迟初始化）
        self.safe_lots_per_grid = None
        self.actual_leverage = None
        self.init_entry_price = None  # 初始开仓价格（从K线数据获取）
    
    def calculate_grids(self):
        """计算网格价位"""
        if self.mode == '等差':
            price_step = (self.upper_bound - self.lower_bound) / self.grid_count
            self.grids = [self.lower_bound + i * price_step for i in range(self.grid_count + 1)]
            self.spacing = price_step  # 等差网格：固定间距
        else:
            ratio = (self.upper_bound / self.lower_bound) ** (1 / self.grid_count)
            self.grids = [self.lower_bound * (ratio ** i) for i in range(self.grid_count + 1)]
            # 等比网格：使用初始价格附近的平均间距作为参考
            self.spacing = self.grids[1] - self.grids[0] if len(self.grids) > 1 else 0
        
        self.grids = sorted(set(self.grids))
        self.grid_count = len(self.grids) - 1  # 更新实际网格数量
    
    def get_grid_index(self, price):
        """获取当前价格所在的网格索引"""
        for i in range(len(self.grids) - 1):
            if self.grids[i] <= price < self.grids[i + 1]:
                return i
        return -1 if price < self.grids[0] else len(self.grids) - 1
    
    def calculate_liquidation_price(self, entry_price, leverage):
        """
        计算强平价
        
        :param entry_price: 开仓价格
        :param leverage: 杠杆倍数
        :return: 强平价
        """
        if self.direction == '多':
            return entry_price * (1 - 1 / leverage)
        else:
            return entry_price * (1 + 1 / leverage)
    
    def calculate_portfolio_avg_entry(self):
        """
        计算所有网格都开仓时的平均开仓价格（价值加权平均）
        
        :return: 平均开仓价格
        """
        if not self.grids:
            return 0
        
        if self.mode == '等差':
            # 等差网格：每个网格张数相同，平均开仓价 = 算术平均
            return sum(self.grids) / len(self.grids)
        else:
            # 等比网格：每个网格名义价值相同（固定保证金开仓）
            # 设每个网格名义价值 = V，则该网格数量 = V / grid_price
            # 平均开仓价 = 总价值 / 总数量 = (n * V) / sum(V / price_i)
            #            = n / sum(1 / price_i)  （调和平均）
            n = len(self.grids)
            harmonic_sum = sum(1.0 / p for p in self.grids)
            return n / harmonic_sum
    
    def calculate_max_safe_leverage_for_extreme_case(self):
        """
        计算极端情况下（所有网格都开仓）的最大安全杠杆
        
        :return: 最大允许杠杆倍数
        """
        avg_entry_price = self.calculate_portfolio_avg_entry()
        
        if self.direction == '多':
            # 多单：liq_price = avg_entry_price * (1 - 1/leverage) <= liquidation_safe_price
            # => leverage <= avg_entry_price / (avg_entry_price - liquidation_safe_price)
            if avg_entry_price <= self.liquidation_safe_price:
                return float('inf')
            return avg_entry_price / (avg_entry_price - self.liquidation_safe_price)
        else:
            # 空单：liq_price = avg_entry_price * (1 + 1/leverage) >= liquidation_safe_price
            # => leverage <= avg_entry_price / (liquidation_safe_price - avg_entry_price)
            if avg_entry_price >= self.liquidation_safe_price:
                return float('inf')
            return avg_entry_price / (self.liquidation_safe_price - avg_entry_price)
    
    def calculate_safe_lots(self, total_margin):
        """
        根据总保证金计算安全的单网格开仓参数
        
        关键逻辑：
        - 等差网格：固定张数开仓（每个网格张数相同）
        - 等比网格：固定名义价值开仓（每个网格名义价值相同，张数随价格变化）
        1. 预估强平价与entry_price无关
        2. 只考虑极端情况：所有网格都开仓时的强平价
        3. 确保极端情况下强平价在安全边界外
        
        :param total_margin: 总投入保证金
        :return: 安全的单网格开仓张数（等差）或基准价格对应张数（等比）
        """
        # 计算极端情况下的最大安全杠杆
        max_safe_leverage = self.calculate_max_safe_leverage_for_extreme_case()
        
        # 确定实际使用的杠杆（取设定杠杆和安全杠杆的较小值）
        self.actual_leverage = min(self.leverage, max_safe_leverage)
        
        # 计算单网格可用保证金
        margin_per_grid = total_margin / self.grid_count
        
        # 计算单网格名义价值（使用实际杠杆）
        position_value_per_grid = margin_per_grid * self.actual_leverage
        
        if self.mode == '等差':
            # 等差网格：固定张数开仓
            # 用平均价格计算基准张数，所有网格统一用这个张数
            avg_grid_price = self.calculate_portfolio_avg_entry()
            position_size_per_grid = position_value_per_grid / avg_grid_price
            lots_per_grid = position_size_per_grid / self.contract_size
            self.safe_lots_per_grid = max(lots_per_grid, self.min_lot_size)
            self.notional_per_grid = None
        else:
            # 等比网格：固定名义价值开仓
            # 保存单网格名义价值，实际开仓张数 = 名义价值 / 价格 / 合约大小
            self.notional_per_grid = position_value_per_grid
            # 用平均价格计算一个基准张数（仅供参考显示）
            avg_grid_price = self.calculate_portfolio_avg_entry()
            reference_size = position_value_per_grid / avg_grid_price
            reference_lots = reference_size / self.contract_size
            self.safe_lots_per_grid = max(reference_lots, self.min_lot_size)
        
        return self.safe_lots_per_grid
    
    def calculate_extreme_liquidation_price(self, total_margin):
        """
        计算极端情况下（所有网格都开仓）的预估强平价
        
        :param total_margin: 总保证金
        :return: 预估强平价, 平均开仓价
        """
        if self.safe_lots_per_grid is None:
            self.calculate_safe_lots(total_margin)
        
        # 计算所有网格都开仓时的平均开仓价格
        avg_entry_price = self.calculate_portfolio_avg_entry()
        
        # 计算组合强平价
        portfolio_liq_price = self.calculate_liquidation_price(avg_entry_price, self.actual_leverage)
        
        return portfolio_liq_price, avg_entry_price
    
    def get_initial_positions(self, init_price, kline_low=None, kline_high=None):
        """
        获取初始建仓位置（以第一根K线收盘价为基准）
        
        :param init_price: 初始开仓价格（K线第一根收盘价）
        :param kline_low: 第一根K线最低价（保留参数但不再使用）
        :param kline_high: 第一根K线最高价（保留参数但不再使用）
        :return: 初始持仓网格索引列表
        """
        self.init_entry_price = init_price
        initial_positions = []
        
        # 检查初始价格是否在网格区间内
        # 如果初始价格不在区间内，不进行建仓
        if init_price < self.lower_bound or init_price > self.upper_bound:
            return initial_positions
        
        if self.direction == '多':
            # 多单：开上所有价格高于等于init_price且低于区间上限的网格
            # grid_price >= init_price 且 grid_price < upper_bound
            # 区间上限(upper_bound)不用于建仓，只是边界
            for i in range(len(self.grids)):
                grid_price = self.grids[i]
                if grid_price >= init_price and grid_price < self.upper_bound:
                    initial_positions.append(i)
        else:
            # 空单：开上所有价格低于等于init_price且高于区间下限的网格
            # grid_price <= init_price 且 grid_price > lower_bound
            # 区间下限(lower_bound)不用于建仓，只是边界
            for i in range(len(self.grids)):
                grid_price = self.grids[i]
                if grid_price <= init_price and grid_price > self.lower_bound:
                    initial_positions.append(i)
        
        return initial_positions
    
    def calculate_max_position_count(self):
        """
        计算最大持仓数量（所有网格都开仓时）
        
        :return: 最大持仓网格数
        """
        return self.grid_count
    
    def verify_strategy_safety(self, total_margin):
        """
        验证策略安全性，分析极端情况
        
        :param total_margin: 总保证金
        :return: 安全分析结果字典
        """
        self.calculate_safe_lots(total_margin)
        
        # 计算极端情况
        extreme_liq_price, avg_entry_price = self.calculate_extreme_liquidation_price(total_margin)
        
        if self.direction == '多':
            is_safe = round(extreme_liq_price) <= round(self.liquidation_safe_price)
        else:
            is_safe = round(extreme_liq_price) >= round(self.liquidation_safe_price)
        
        results = {
            'actual_leverage': self.actual_leverage,
            'safe_lots_per_grid': self.safe_lots_per_grid,
            'liquidation_safe_price': self.liquidation_safe_price,
            'direction': self.direction,
            'extreme_case': {
                'avg_entry_price': avg_entry_price,
                'liquidation_price': extreme_liq_price,
                'max_position_count': self.grid_count,
                'total_lots': self.grid_count * self.safe_lots_per_grid,
                'is_safe': is_safe
            },
            'safety_violation': None
        }
        
        if not is_safe:
            results['safety_violation'] = {
                'reason': f"极端情况下预估强平价不满足安全要求",
                'actual': extreme_liq_price,
                'required': self.liquidation_safe_price,
                'suggestion': f"请降低杠杆或调整价格区间"
            }
        
        return results
    
    def calculate_position_lots(self, total_margin):
        """计算单网格开仓量（以张数为单位）"""
        if self.safe_lots_per_grid is None:
            self.calculate_safe_lots(total_margin)
        return self.safe_lots_per_grid
    
    def lots_to_size(self, lots):
        """将张数转换为实际数量（BTC/ETH）"""
        return lots * self.contract_size
    
    def size_to_lots(self, size):
        """将实际数量转换为张数"""
        return size / self.contract_size
    
    def get_grid_price(self, index):
        """获取指定索引的网格价格"""
        if 0 <= index < len(self.grids):
            return self.grids[index]
        return None
    
    def print_strategy_params(self, total_margin, init_price=None, print_func=None):
        """打印策略参数和安全分析"""
        # 使用自定义打印函数，默认为print
        p = print_func if print_func is not None else print
        
        p(f"交易方向: {self.direction}")
        p(f"价格区间: [{self.lower_bound:.2f}, {self.upper_bound:.2f}]")
        p(f"网格数量: {self.grid_count}")
        p(f"网格间距: {self.spacing:.3f}")
        p(f"网格模式: {self.mode}")
        p(f"设定杠杆: {self.leverage}x")
        p(f"合约类型: {self.contract_type}")
        p(f"合约规格: 1张 = {self.contract_size} {self.contract_type}")
        p(f"最小交易单位: {self.min_lot_size} 张")
        p(f"限价手续费: {self.maker_fee * 100:.4f}%")
        p(f"市价手续费: {self.taker_fee * 100:.4f}%")
        p(f"强平价安全偏移: {self.SAFETY_OFFSET * 100:.0f}%")
        
        if self.direction == '多':
            p(f"强平价安全边界: <= {self.liquidation_safe_price:.2f}")
            p(f"  (区间下限 {self.lower_bound:.2f} 的 {100 - self.SAFETY_OFFSET*100}%)")
            p(f"风险特征: 价格逼近区间下沿时持仓最多，风险最大")
        else:
            p(f"强平价安全边界: >= {self.liquidation_safe_price:.2f} (区间上限 {self.upper_bound:.2f} 的 {100 + self.SAFETY_OFFSET*100}%)")
        
        # 计算安全参数
        self.calculate_safe_lots(total_margin)
        
        p(f"\n单网格开仓参数:")
        p(f"  实际杠杆: {self.actual_leverage:.2f}x")
        p(f"  开仓张数: {self.safe_lots_per_grid:.2f} 张")
        position_amt = self.lots_to_size(self.safe_lots_per_grid)
        # 根据数值大小动态决定小数位，确保最小单位能清晰显示
        if position_amt < 0.001:
            prec = 8
        elif position_amt < 0.01:
            prec = 6
        elif position_amt < 1:
            prec = 4
        else:
            prec = 2
        # 显示时保留4位小数，但内部计算仍使用原始精度
        display_amt = f"{position_amt:.4f}"
        p(f"  开仓数量: {display_amt} {self.contract_type}")
        
        # 预估强平价（所有网格都开仓时）
        safety_results = self.verify_strategy_safety(total_margin)
        extreme = safety_results['extreme_case']
        
        p(f"\n预估强平价 (所有网格都开仓时):")
        p(f"  预估强平价: {extreme['liquidation_price']:.2f}")
        if self.direction == '多':
            p(f"  安全边界: <= {self.liquidation_safe_price:.2f}")
        else:
            p(f"  安全边界: >= {self.liquidation_safe_price:.2f}")
        
        if extreme['is_safe']:
            p(f"  ✓ 预估强平价满足安全要求")
        else:
            p(f"  ✗ 预估强平价不满足安全要求")
            if 'safety_violation' in safety_results and safety_results['safety_violation']:
                p(f"    建议: {safety_results['safety_violation']['suggestion']}")
        
        # 如果有初始开仓价格，显示初始建仓信息
        if init_price is not None:
            initial_positions = self.get_initial_positions(init_price)
            p(f"\n初始建仓信息 (entry_price = {init_price:.2f}):")
            p(f"  初始建仓网格数量: {len(initial_positions)}")
            p(f"  初始持仓张数: {len(initial_positions) * self.safe_lots_per_grid:.2f} 张")

    
    def get_strategy_summary(self, total_margin, init_price=None):
        """获取策略摘要（用于回测报告）"""
        self.calculate_safe_lots(total_margin)
        safety_results = self.verify_strategy_safety(total_margin)
        
        initial_positions = self.get_initial_positions(init_price) if init_price else []
        
        summary = {
            'direction': self.direction,
            'upper_bound': self.upper_bound,
            'lower_bound': self.lower_bound,
            'grid_count': self.grid_count,
            'mode': self.mode,
            'configured_leverage': self.leverage,
            'actual_leverage': self.actual_leverage,
            'liquidation_safe_price': self.liquidation_safe_price,
            'safe_lots_per_grid': self.safe_lots_per_grid,
            'extreme_case': safety_results['extreme_case'],
            'is_safe': safety_results['extreme_case']['is_safe'],
            'initial_positions': initial_positions,
            'init_entry_price': init_price
        }
        
        return summary