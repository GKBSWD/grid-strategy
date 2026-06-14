from modules.kline_data import KlineData
from modules.grid_strategy import GridStrategy
from modules.backtester import Backtester
from modules.visualization import Visualization
from datetime import datetime
import argparse
import os
import subprocess
import time

def parse_args():
    parser = argparse.ArgumentParser(description='合约网格策略回测')
    
    parser.add_argument('--symbol', type=str, default='ETH', help='交易品种: BTC, ETH, SOL, AVAX 等')
    parser.add_argument('--lower_bound', type=float, default=1110.88, help='价格区间下限')
    parser.add_argument('--upper_bound', type=float, default=2221.78 , help='价格区间上限')
    parser.add_argument('--grid_count', type=int, default=200, help='网格数量')
    parser.add_argument('--grid_mode', type=str, default='等差', choices=['等差', '等比'], help='网格模式')
    parser.add_argument('--leverage', type=int, default=3, help='杠杆倍数')
    parser.add_argument('--direction', type=str, default='多', choices=['多', '空'], help='交易方向')
    parser.add_argument('--total_margin', type=float, default=10000, help='总保证金')
    parser.add_argument('--start_time', type=str, default='2026-05-28 00:00:00', help='回测起始时间')
    parser.add_argument('--end_time', type=str, default='2026-06-11 00:00:00', help='回测结束时间')
    parser.add_argument('--kline_period', type=str, default='1m', help='K线周期')
    
    # 合约规格相关参数（可选）
    parser.add_argument('--contract_size', type=float, default=0.1, help='合约规格：1张等于多少标的（如BTC为0.01，ETH为0.1）')
    parser.add_argument('--min_lot_size', type=float, default=0.01, help='最小交易单位（张数，如0.01）')
    parser.add_argument('--taker_fee', type=float, default=0.0005, help='市价手续费比例（如0.00075）')
    parser.add_argument('--maker_fee', type=float, default=0.0002, help='限价手续费比例（如0.00025）')
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    # 验证价格区间参数
    if args.lower_bound >= args.upper_bound:
        print(f"错误: 价格区间下限({args.lower_bound})必须小于价格区间上限({args.upper_bound})")
        return
    
    start_time = datetime.strptime(args.start_time, '%Y-%m-%d %H:%M:%S')
    end_time = datetime.strptime(args.end_time, '%Y-%m-%d %H:%M:%S')
    
    print(f"正在获取 {args.symbol} K线数据...")
    kline_data = KlineData()
    df = kline_data.get_kline_data(args.symbol, start_time, end_time, args.kline_period)
    
    if df.empty:
        print("未获取到K线数据，回测终止")
        return
    
    print(f"获取到 {len(df)} 条K线数据")
    
    # 计算回测时间长度
    first_time = df.iloc[0]['timestamp']
    last_time = df.iloc[-1]['timestamp']
    time_diff = last_time - first_time
    
    days = time_diff.days
    hours = time_diff.seconds // 3600
    minutes = (time_diff.seconds % 3600) // 60
    
    print(f"回测时长 {days}天 {hours}小时 {minutes}分钟")
    
    # 获取初始开仓价格（第一条K线的收盘价）
    init_price = df.iloc[0]['close']
    
    strategy = GridStrategy(
        upper_bound=args.upper_bound,
        lower_bound=args.lower_bound,
        grid_count=args.grid_count,
        mode=args.grid_mode,
        leverage=args.leverage,
        direction=args.direction,
        contract_type=args.symbol,
        contract_size=args.contract_size,
        min_lot_size=args.min_lot_size,
        taker_fee=args.taker_fee,
        maker_fee=args.maker_fee
    )
    
    # 传递初始开仓价格给策略
    strategy.print_strategy_params(args.total_margin, init_price)
    
    backtester = Backtester(strategy, df, args.total_margin)
    results = backtester.run()
    
    backtester.print_results(results)
    
    # 生成文件名：标的名_起始日期_结束日期（日期只取到天）
    start_date_str = start_time.strftime('%Y-%m-%d')
    end_date_str = end_time.strftime('%Y-%m-%d')
    file_name = f'{args.symbol}_{start_date_str}_{end_date_str}'
    
    backtester.trade_record.save_to_excel(f'{file_name}.xlsx')
    
    visualization = Visualization(results)
    html_path = visualization.generate_html_report(args.symbol, file_name)
    
    # 使用Edge浏览器自动打开HTML报告
    if os.path.exists(html_path):
        # 等待文件完全写入
        time.sleep(1)
        # 获取绝对路径
        abs_path = os.path.abspath(html_path)
        # 使用start命令直接打开文件（更可靠）
        try:
            # 使用cmd的start命令打开，系统会用默认程序打开HTML文件
            subprocess.Popen(['start', '', abs_path], shell=True, cwd=os.getcwd())
            print(f"已打开报告: {abs_path}")
        except Exception as e:
            print(f"打开报告失败: {e}")

if __name__ == '__main__':
    main()