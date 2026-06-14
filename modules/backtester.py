import pandas as pd
import numpy as np
from datetime import datetime
import os
from tqdm import tqdm

class TradeRecord:
    def __init__(self):
        self.records = []
    
    def add_record(self, kline_time, action, price, lots, margin, entry_price, 
                   grid_profit, grid_fee, cumulative_pnl, cumulative_fee, return_rate, grid_index):
        self.records.append({
            'K线时间': kline_time,
            '交易类型': action,
            '成交价格': price,
            '开仓价格': entry_price,
            '持仓张数': lots,
            '保证金': margin,
            '当笔网格利润': grid_profit,
            '当笔手续费': grid_fee,
            '累积利润': cumulative_pnl,
            '累积手续费': cumulative_fee,
            '累积收益率': return_rate,
            '网格索引': grid_index
        })
    
    def to_dataframe(self):
        return pd.DataFrame(self.records)
    
    def save_to_excel(self, filepath):
        df = self.to_dataframe()
        output_dir = os.path.dirname(filepath)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        try:
            df.to_excel(filepath, index=False)
            print(f"交易记录已保存到: {filepath}")
        except PermissionError:
            # 文件被其他程序占用（通常是 Excel 打开了）
            alt_filepath = filepath.replace('.xlsx', f'_{datetime.now().strftime("%H%M%S")}.xlsx')
            print(f"[警告] 无法写入 {filepath}（文件可能被 Excel 打开）")
            try:
                df.to_excel(alt_filepath, index=False)
                print(f"已保存到备用文件名: {alt_filepath}")
            except Exception as e2:
                print(f"[错误] 备用保存也失败: {e2}")

class Backtester:
    def __init__(self, strategy, data, total_margin):
        self.strategy = strategy
        self.data = data
        self.total_margin = total_margin
        self.available_margin = total_margin
        self.position_margin = 0
        self.positions = {}  # grid_index -> {'price', 'lots', 'amount', 'margin', 'open_time'}
        self.trade_record = TradeRecord()
        self.realized_pnl = 0  # 已实现盈亏（所有平仓利润之和）
        self.unrealized_pnl = 0  # 未实现盈亏（当前持仓按最后收盘价计算）
        self.grid_arbitrage_count = 0
        self.total_fee = 0  # 总手续费（初始建仓市价费 + 后续交易限价费）
        self.initial_fee = 0  # 初始建仓手续费（市价）
        self.grid_trade_fee = 0  # 网格交易手续费（限价，不含初始建仓）
        self.equity_curve = []
        self.pnl_curve = []
        self.arbitrage_count_curve = []
        self.price_curve = []  # K线收盘价曲线
        self.initial_phase = True  # 初始建仓阶段标志
    
    @property
    def total_pnl(self):
        """总盈亏 = (已实现盈亏 - 总手续费) + 未实现盈亏"""
        return (self.realized_pnl - self.total_fee) + self.unrealized_pnl
    
    @property
    def equity(self):
        """账户权益 = 可用保证金 + 持仓保证金 + 总盈亏"""
        return self.available_margin + self.position_margin + self.total_pnl
    
    def update_unrealized_pnl(self, price):
        """更新未实现盈亏"""
        unrealized_pnl = 0
        for grid_idx, pos in self.positions.items():
            entry_price = pos['price']
            position_size = pos['amount']
            
            if self.strategy.direction == '多':
                unrealized_pnl += (price - entry_price) * position_size
            else:
                unrealized_pnl += (entry_price - price) * position_size
        
        self.unrealized_pnl = unrealized_pnl
    
    def open_position(self, kline_time, price, grid_index):
        """开仓"""
        if grid_index in self.positions:
            return 0
        
        position_lots = self.strategy.calculate_position_lots(self.total_margin)
        if position_lots <= 0:
            return 0
        
        position_size = self.strategy.lots_to_size(position_lots)
        margin_needed = price * position_size / self.strategy.actual_leverage
        
        if margin_needed > self.available_margin:
            return 0
        
        # 手续费区分：初始建仓使用市价手续费(taker_fee)，后续开仓使用限价手续费(maker_fee)
        if self.initial_phase:
            fee = price * position_size * self.strategy.taker_fee
            self.initial_fee += fee
        else:
            fee = price * position_size * self.strategy.maker_fee
            self.grid_trade_fee += fee
        
        self.total_fee += fee
        
        self.positions[grid_index] = {
            'price': price,
            'lots': position_lots,
            'amount': position_size,
            'margin': margin_needed,
            'open_time': kline_time
        }
        
        self.available_margin -= margin_needed
        self.position_margin += margin_needed
        
        # 计算当前收益率（已实现利润 = 平仓利润 - 总手续费）
        realized_pnl_with_fee = self.realized_pnl - self.total_fee
        return_rate = (realized_pnl_with_fee + self.unrealized_pnl) / self.total_margin * 100
        
        self.trade_record.add_record(
            kline_time=kline_time,
            action='开仓',
            price=price,
            lots=position_lots,
            margin=margin_needed,
            entry_price=price,
            grid_profit=0,
            grid_fee=fee,
            cumulative_pnl=self.total_pnl,
            cumulative_fee=self.total_fee,
            return_rate=return_rate,
            grid_index=grid_index
        )
        
        return position_lots
    
    def close_position(self, kline_time, price, grid_index):
        """平仓"""
        if grid_index not in self.positions:
            return 0
        
        pos = self.positions[grid_index]
        position_lots = pos['lots']
        position_size = pos['amount']
        entry_price = pos['price']
        margin_needed = pos['margin']
        
        if self.strategy.direction == '多':
            profit = (price - entry_price) * position_size
        else:
            profit = (entry_price - price) * position_size
        
        # 平仓使用限价手续费(maker_fee)
        fee = price * position_size * self.strategy.maker_fee
        self.total_fee += fee
        self.grid_trade_fee += fee  # 平仓手续费计入网格交易手续费
        
        # 已实现利润 = 平仓利润（不排除初始建仓带来的超额收益）
        self.realized_pnl += profit
        self.available_margin += margin_needed
        self.position_margin -= margin_needed
        
        del self.positions[grid_index]
        
        self.grid_arbitrage_count += 1
        
        # 计算当前收益率（已实现利润 = 平仓利润 - 总手续费）
        realized_pnl_with_fee = self.realized_pnl - self.total_fee
        return_rate = (realized_pnl_with_fee + self.unrealized_pnl) / self.total_margin * 100
        
        self.trade_record.add_record(
            kline_time=kline_time,
            action='平仓',
            price=price,
            lots=position_lots,
            margin=margin_needed,
            entry_price=entry_price,
            grid_profit=profit,
            grid_fee=fee,
            cumulative_pnl=self.total_pnl,
            cumulative_fee=self.total_fee,
            return_rate=return_rate,
            grid_index=grid_index
        )
        
        return position_lots
    
    def run(self, progress_callback=None, stop_callback=None):
        """运行回测
        
        Args:
            progress_callback: 进度回调函数，接收当前进度百分比 (0-100)
            stop_callback: 停止回调函数，返回 True 时立即终止回测
        """
        """运行回测"""
        if self.data.empty:
            print("K线数据为空，无法进行回测")
            return None
        
        first_row = self.data.iloc[0]
        first_time = first_row['timestamp']
        first_close = first_row['close']
        first_low = first_row['low']
        first_high = first_row['high']
        
        # 获取初始建仓网格列表
        initial_positions = self.strategy.get_initial_positions(first_close, first_low, first_high)
        
        # 初始建仓：开上所有符合条件的网格，使用初始价(first_close)作为统一开仓价
        # 例如初始价50，网格点50~99都以50开仓，而非各自网格点价格
        for grid_idx in initial_positions:
            # 停止检查点
            if stop_callback and stop_callback():
                return None
            self.open_position(first_time, first_close, grid_idx)
        
        # 更新初始未实现盈亏
        self.update_unrealized_pnl(first_close)
        
        # 初始建仓阶段结束
        self.initial_phase = False
        
        # 记录初始状态
        self.equity_curve.append({'timestamp': first_time, 'equity': self.equity})
        self.pnl_curve.append({'timestamp': first_time, 'pnl': self.total_pnl})
        self.arbitrage_count_curve.append({'timestamp': first_time, 'count': self.grid_arbitrage_count})
        self.price_curve.append({'timestamp': first_time, 'price': first_close})
        
        # 从第二根K线开始遍历
        total_rows = len(self.data.iloc[1:])
        last_progress_percent = -1  # 记录上次更新的进度百分比
        
        # 如果有progress_callback，使用简单的range循环；否则使用tqdm显示终端进度
        if progress_callback:
            data_iter = self.data.iloc[1:].iterrows()
        else:
            data_iter = tqdm(self.data.iloc[1:].iterrows(), total=total_rows, desc='回测进度', unit='K线')
        
        for i, (idx, row) in enumerate(data_iter):
            # 计算当前进度百分比（基于已回测的K线数占总K线数的比例）
            if progress_callback and total_rows > 0:
                current_progress_percent = int((i + 1) / total_rows * 100)  # 只取整数部分
                # 只有当进度百分比增加至少2%时才更新（减少刷新次数）
                if current_progress_percent // 2 > last_progress_percent // 2:
                    progress_callback(current_progress_percent)
                    last_progress_percent = current_progress_percent
            
            # 停止检查点
            if stop_callback and stop_callback():
                return None
            
            self.current_time = row['timestamp']
            open_price = row['open']
            high = row['high']
            low = row['low']
            close = row['close']
            
            # 判断阳线还是阴线
            is_bullish = close >= open_price
            
            # 创建网格持仓状态表：True表示有持仓，False表示无持仓
            # 注意：此表在每一步交易后实时更新
            has_position = {i: (i in self.positions) for i in range(len(self.strategy.grids))}
            
            if is_bullish:
                # 阳线价格波动顺序：开盘价 → 最低价 → 最高价 → 收盘价
                # 单K线内部无限制：新开的仓位在同一K线内也可以平仓
                # 单向网格：做多就只有多单开仓/平仓，做空就只有空单开仓/平仓
                
                # 阶段1: 开盘价 -> 最低价（价格下跌）
                # 按价格从高到低检查（价格下跌先触发高价网格）
                for grid_idx in range(len(self.strategy.grids)-1, -1, -1):
                    grid_price = self.strategy.grids[grid_idx]
                    if open_price >= grid_price >= low:
                        if self.strategy.direction == '多':
                            # 多单：价格下跌到网格点时，若该点无持仓则开多单（低买）
                            # 上界不建仓
                            if not has_position[grid_idx] and grid_price < self.strategy.upper_bound:
                                if self.open_position(self.current_time, grid_price, grid_idx) > 0:
                                    has_position[grid_idx] = True
                        else:
                            # 空单：价格下跌到网格点时，平后一个（更高价格）网格的空单（低买获利）
                            next_grid_idx = grid_idx + 1
                            if next_grid_idx < len(self.strategy.grids) and has_position[next_grid_idx]:
                                if self.close_position(self.current_time, grid_price, next_grid_idx) > 0:
                                    has_position[next_grid_idx] = False
                
                # 阶段2: 最低价 -> 最高价（价格上涨）
                # 按价格从低到高检查（价格上涨先触发低价网格）
                for grid_idx in range(len(self.strategy.grids)):
                    grid_price = self.strategy.grids[grid_idx]
                    if low <= grid_price <= high:
                        if self.strategy.direction == '多':
                            # 多单：价格上涨到网格点时，平前一个（更低价格）网格的多单（高卖获利）
                            prev_grid_idx = grid_idx - 1
                            if prev_grid_idx >= 0 and has_position[prev_grid_idx]:
                                if self.close_position(self.current_time, grid_price, prev_grid_idx) > 0:
                                    has_position[prev_grid_idx] = False
                        else:
                            # 空单：价格上涨到网格点时，若该点无持仓则开空单（高卖）
                            # 下界不建仓
                            if not has_position[grid_idx] and grid_price > self.strategy.lower_bound:
                                if self.open_position(self.current_time, grid_price, grid_idx) > 0:
                                    has_position[grid_idx] = True
                
                # 阶段3: 最高价 -> 收盘价（价格回落）
                # 按价格从高到低检查（价格回落先触发高价网格）
                for grid_idx in range(len(self.strategy.grids)-1, -1, -1):
                    grid_price = self.strategy.grids[grid_idx]
                    if high >= grid_price >= close:
                        if self.strategy.direction == '多':
                            # 多单：价格回落到网格点时，若该点无持仓则开多单（低买）
                            # 上界不建仓
                            if not has_position[grid_idx] and grid_price < self.strategy.upper_bound:
                                if self.open_position(self.current_time, grid_price, grid_idx) > 0:
                                    has_position[grid_idx] = True
                        else:
                            # 空单：价格回落到网格点时，平后一个（更高价格）网格的空单（低买获利）
                            next_grid_idx = grid_idx + 1
                            if next_grid_idx < len(self.strategy.grids) and has_position[next_grid_idx]:
                                if self.close_position(self.current_time, grid_price, next_grid_idx) > 0:
                                    has_position[next_grid_idx] = False
            
            else:
                # 阴线价格波动顺序：开盘价 → 最高价 → 最低价 → 收盘价
                # 单K线内部无限制：新开的仓位在同一K线内也可以平仓
                # 单向网格：做多就只有多单开仓/平仓，做空就只有空单开仓/平仓
                
                # 阶段1: 开盘价 -> 最高价（价格上涨）
                # 按价格从低到高检查（价格上涨先触发低价网格）
                for grid_idx in range(len(self.strategy.grids)):
                    grid_price = self.strategy.grids[grid_idx]
                    if open_price <= grid_price <= high:
                        if self.strategy.direction == '多':
                            # 多单：价格上涨到网格点时，平前一个（更低价格）网格的多单（高卖获利）
                            prev_grid_idx = grid_idx - 1
                            if prev_grid_idx >= 0 and has_position[prev_grid_idx]:
                                if self.close_position(self.current_time, grid_price, prev_grid_idx) > 0:
                                    has_position[prev_grid_idx] = False
                        else:
                            # 空单：价格上涨到网格点时，若该点无持仓则开空单（高卖）
                            # 下界不建仓
                            if not has_position[grid_idx] and grid_price > self.strategy.lower_bound:
                                if self.open_position(self.current_time, grid_price, grid_idx) > 0:
                                    has_position[grid_idx] = True
                
                # 阶段2: 最高价 -> 最低价（价格下跌）
                # 按价格从高到低检查（价格下跌先触发高价网格）
                for grid_idx in range(len(self.strategy.grids)-1, -1, -1):
                    grid_price = self.strategy.grids[grid_idx]
                    if high >= grid_price >= low:
                        if self.strategy.direction == '多':
                            # 多单：价格下跌到网格点时，若该点无持仓则开多单（低买）
                            # 上界不建仓
                            if not has_position[grid_idx] and grid_price < self.strategy.upper_bound:
                                if self.open_position(self.current_time, grid_price, grid_idx) > 0:
                                    has_position[grid_idx] = True
                        else:
                            # 空单：价格下跌到网格点时，平后一个（更高价格）网格的空单（低买获利）
                            next_grid_idx = grid_idx + 1
                            if next_grid_idx < len(self.strategy.grids) and has_position[next_grid_idx]:
                                if self.close_position(self.current_time, grid_price, next_grid_idx) > 0:
                                    has_position[next_grid_idx] = False
                
                # 阶段3: 最低价 -> 收盘价（价格反弹）
                # 按价格从低到高检查（价格反弹先触发低价网格）
                for grid_idx in range(len(self.strategy.grids)):
                    grid_price = self.strategy.grids[grid_idx]
                    if low <= grid_price <= close:
                        if self.strategy.direction == '多':
                            # 多单：价格反弹到网格点时，平前一个（更低价格）网格的多单（高卖获利）
                            prev_grid_idx = grid_idx - 1
                            if prev_grid_idx >= 0 and has_position[prev_grid_idx]:
                                if self.close_position(self.current_time, grid_price, prev_grid_idx) > 0:
                                    has_position[prev_grid_idx] = False
                        else:
                            # 空单：价格反弹到网格点时，若该点无持仓则开空单（高卖）
                            # 下界不建仓
                            if not has_position[grid_idx] and grid_price > self.strategy.lower_bound:
                                if self.open_position(self.current_time, grid_price, grid_idx) > 0:
                                    has_position[grid_idx] = True
            
            # 更新未实现盈亏（基于当前K线收盘价）
            self.update_unrealized_pnl(close)
            
            # 记录当前状态
            self.equity_curve.append({'timestamp': self.current_time, 'equity': self.equity})
            self.pnl_curve.append({'timestamp': self.current_time, 'pnl': self.total_pnl})
            self.arbitrage_count_curve.append({'timestamp': self.current_time, 'count': self.grid_arbitrage_count})
            self.price_curve.append({'timestamp': self.current_time, 'price': close})
        
        return self.get_results()
    
    def get_results(self):
        """获取回测结果"""
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
        
        # 计算回测周期（使用数据的实际时间范围）
        if not self.data.empty:
            start_time = self.data['timestamp'].iloc[0]
            end_time = self.data['timestamp'].iloc[-1]
            days = (end_time - start_time).total_seconds() / (24 * 3600)
            # 确保至少有一天
            days = max(days, 1)
        else:
            days = 1
        
        if not equity_df.empty:
            # 计算最大回撤
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak']
            max_drawdown = equity_df['drawdown'].min()
        else:
            max_drawdown = 0
        
        # 最终权益
        final_equity = self.equity
        
        # 总收益率
        return_rate = ((final_equity - self.total_margin) / self.total_margin) * 100
        
        # 年化收益率（使用单利计算，更稳健且适合网格策略）
        # 公式：年化收益率 = 总收益率 × (365 / 回测天数)
        if days > 0:
            annualized_return = return_rate * (365 / days)
        else:
            annualized_return = 0
        
        # 网格套利利润：只计算单纯套利收益（排除初始建仓带来的额外收益）
        # 单纯套利收益 = 套利次数 × 网格间距 × 单网格交易数量 - 网格交易手续费（不含初始建仓手续费）
        grid_spacing = self.strategy.spacing
        
        # 获取单网格实际交易数量
        position_lots = self.strategy.safe_lots_per_grid if self.strategy.safe_lots_per_grid else 0.01
        position_size = position_lots * self.strategy.contract_size
        
        # 网格套利利润 = 套利次数 × 网格间距 × 单网格数量 - 网格交易手续费（限价手续费）
        pure_arbitrage_pnl = self.grid_arbitrage_count * grid_spacing * position_size - self.grid_trade_fee
        
        if days > 0 and self.total_margin > 0:
            grid_annualized_return = (pure_arbitrage_pnl / self.total_margin) * (365 / days) * 100
        else:
            grid_annualized_return = 0
        
        # 已实现利润 = 所有平仓利润 - 总手续费（初始建仓市价费 + 后续交易限价费）
        realized_pnl_with_fee = self.realized_pnl - self.total_fee
        
        return {
            'initial_margin': self.total_margin,
            'final_equity': final_equity,
            'total_pnl': self.total_pnl,  # 总利润 = (已实现利润 - 手续费) + 未实现利润
            'realized_pnl': realized_pnl_with_fee,  # 已实现利润 = 平仓收益 - 总手续费
            'unrealized_pnl': self.unrealized_pnl,
            'grid_arbitrage_pnl': pure_arbitrage_pnl,  # 网格套利利润 = 套利次数×网格间距×单网格数量 - 网格交易手续费
            'total_fee': self.total_fee,
            'grid_arbitrage_count': self.grid_arbitrage_count,
            'return_rate': return_rate,
            'annualized_return': annualized_return,
            'grid_annualized_return': grid_annualized_return,
            'max_drawdown': max_drawdown,
            'open_positions': len(self.positions),
            'equity_curve': self.equity_curve,
            'pnl_curve': self.pnl_curve,
            'arbitrage_count_curve': self.arbitrage_count_curve,
            'price': self.price_curve
        }
    
    def print_results(self, results, print_func=None):
        """打印回测结果"""
        # 使用自定义打印函数，默认为print
        p = print_func if print_func is not None else print
        
        p(f"最终权益: {results['final_equity']:.2f} USDT")
        p(f"总利润: {results['total_pnl']:.2f} USDT")
        p(f"  - 已实现利润: {results['realized_pnl']:.2f} USDT")
        p(f"  - 未实现利润: {results['unrealized_pnl']:.2f} USDT")
        p(f"  - 网格套利利润: {results['grid_arbitrage_pnl']:.2f} USDT")
        p(f"总手续费: {results['total_fee']:.2f} USDT")
        p(f"网格套利次数: {results['grid_arbitrage_count']} 次")
        p(f"收益率: {results['return_rate']:.2f}%")
        p(f"年化收益率: {results['annualized_return']:.2f}%")
        p(f"网格套利年化收益率: {results['grid_annualized_return']:.2f}%")
        p(f"最大回撤: {results['max_drawdown']:.2%}")
        p(f"未平仓持仓: {results['open_positions']} 个")
        p("=" * 40)