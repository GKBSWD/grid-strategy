import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import os

class Visualization:
    def __init__(self, results):
        self.results = results
    
    def generate_html_report(self, symbol, file_name, output_dir='results'):
        """生成HTML报告，包含交互式图表"""
        initial_margin = self.results['initial_margin']
        
        # 将列表转换为DataFrame
        equity_df = pd.DataFrame(self.results['equity_curve'])
        pnl_df = pd.DataFrame(self.results['pnl_curve'])
        arbitrage_df = pd.DataFrame(self.results['arbitrage_count_curve'])
        
        # 计算收益率
        equity_df['return_rate'] = ((equity_df['equity'] - initial_margin) / initial_margin) * 100
        
        # 合并数据
        df = equity_df.merge(pnl_df, on='timestamp', how='left')
        df['pnl'] = df['pnl'].ffill()
        
        # 合并套利次数数据
        df = df.merge(arbitrage_df, on='timestamp', how='left')
        df['count'] = df['count'].ffill()
        
        # 合并价格数据
        if 'price' in self.results:
            price_df = pd.DataFrame(self.results['price'])
            df = df.merge(price_df, on='timestamp', how='left')
            df['price'] = df['price'].ffill()
        
        # ========== 第一个图：收益率曲线 ==========
        fig1 = go.Figure()
        
        # 收益率曲线（左侧纵轴）
        fig1.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['return_rate'],
            mode='lines',
            name='收益率',
            line=dict(color='#ff7f0e', width=2),
            hovertemplate='时间: %{x}<br>收益率: %{y:.2f}%<br>收益额: $%{customdata[0]:.2f}<br>权益: $%{customdata[1]:.2f}<br>标的价格: $%{customdata[2]:.2f}<extra></extra>',
            customdata=df[['pnl', 'equity', 'price']]
        ))
        
        # K线收盘价曲线（右侧纵轴，可开关）
        if 'price' in self.results:
            fig1.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                mode='lines',
                name=f'{symbol}',
                line=dict(color='#1f77b4', width=2),
                yaxis='y2',
                visible='legendonly',  # 默认隐藏，通过图例开关控制
                hovertemplate='时间: %{x}<br>价格: $%{y:.2f}<extra></extra>'  # 只显示时间和价格
        ))
        
        # 计算收益率纵轴范围（增大显示范围，上下各留40%余量）
        if not df['return_rate'].empty:
            min_rate = df['return_rate'].min()
            max_rate = df['return_rate'].max()
            range_padding = (max_rate - min_rate) * 0.4 if (max_rate - min_rate) != 0 else 15
            y_min = min_rate - range_padding
            y_max = max_rate + range_padding
        else:
            y_min = -30
            y_max = 30
        
        fig1.update_layout(
            title=f'{symbol} 收益率曲线',
            title_font=dict(size=18, color='#333'),
            title_x=0.5,  # 标题水平居中
            xaxis_title='时间',
            xaxis_title_font=dict(size=16),  # 增大横轴标题文字大小
            xaxis_tickformat='%Y-%m-%d',  # 横轴只显示日期（年-月-日）
            xaxis_tickfont=dict(size=14),  # 增大横轴刻度文字大小
            yaxis_title='收益率 (%)',
            yaxis_title_font=dict(size=16),  # 增大纵轴标题文字大小
            yaxis_tickfont=dict(size=14),  # 增大纵轴刻度文字大小
            yaxis_range=[y_min, y_max],
            yaxis2=dict(
                title=symbol,  # 标的价格轴只用标的名
                title_font=dict(size=16),  # 增大右侧纵轴标题文字大小
                tickfont=dict(size=14),  # 增大右侧纵轴刻度文字大小
                overlaying='y',
                side='right'
            ),
            hovermode='closest',
            hoverlabel=dict(
                bgcolor='white',  # 白色背景
                bordercolor='gray',
                font=dict(color='black')
            ),
            template='plotly_white',
            font=dict(family='Arial, sans-serif', size=12),
            margin=dict(l=140, r=140, t=60, b=60),  # 增大边距以容纳更大的文字
            autosize=True,  # 自动调整大小，自适应容器宽度
            height=800,  # 增大为原来的1.6倍（500 * 1.6 = 800）
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=-0.15,  # 缩小legend距离横轴的距离
                xanchor='center',
                x=0.5,
                font=dict(size=14)  # 增大图例文字大小
            )
        )
        
        # ========== 第二个图：网格套利次数曲线 ==========
        fig2 = go.Figure()
        
        # 套利次数曲线（左侧纵轴）
        fig2.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['count'],
            mode='lines',
            name='套利次数',
            line=dict(color='#d62728', width=2),
            hovertemplate='时间: %{x}<br>套利次数: %{y}<br>标的价格: $%{customdata:.2f}<extra></extra>',
            customdata=df['price']
        ))
        
        # K线收盘价曲线（右侧纵轴，可开关）
        if 'price' in self.results:
            fig2.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                mode='lines',
                name=f'{symbol}',
                line=dict(color='#1f77b4', width=2),
                yaxis='y2',
                visible='legendonly',  # 默认隐藏，通过图例开关控制
                hovertemplate='时间: %{x}<br>价格: $%{y:.2f}<extra></extra>'  # 只显示时间和价格
        ))
        
        # 计算套利次数纵轴范围（增大显示范围，上下各留20%余量）
        if not df['count'].empty:
            min_count = df['count'].min()
            max_count = df['count'].max()
            count_range_padding = (max_count - min_count) * 0.2 if (max_count - min_count) != 0 else 100
            count_y_min = min_count - count_range_padding
            count_y_max = max_count + count_range_padding
        else:
            count_y_min = 0
            count_y_max = 100
        
        fig2.update_layout(
            title='网格套利次数曲线',
            title_font=dict(size=18, color='#333'),
            title_x=0.5,  # 标题水平居中
            xaxis_title='时间',
            xaxis_title_font=dict(size=16),  # 增大横轴标题文字大小
            xaxis_tickformat='%Y-%m-%d',  # 横轴只显示日期（年-月-日）
            xaxis_tickfont=dict(size=14),  # 增大横轴刻度文字大小
            yaxis_title='套利次数',
            yaxis_title_font=dict(size=16),  # 增大纵轴标题文字大小
            yaxis_tickfont=dict(size=14),  # 增大纵轴刻度文字大小
            yaxis_range=[max(0, count_y_min), count_y_max],  # 套利次数不能为负
            yaxis2=dict(
                title=symbol,  # 标的价格轴只用标的名
                title_font=dict(size=16),  # 增大右侧纵轴标题文字大小
                tickfont=dict(size=14),  # 增大右侧纵轴刻度文字大小
                overlaying='y',
                side='right'
            ),
            hovermode='closest',
            hoverlabel=dict(
                bgcolor='white',  # 白色背景
                bordercolor='gray',
                font=dict(color='black')
            ),
            template='plotly_white',
            font=dict(family='Arial, sans-serif', size=12),
            margin=dict(l=140, r=140, t=60, b=60),  # 增大边距以容纳更大的文字
            autosize=True,  # 自动调整大小，自适应容器宽度
            height=800,  # 增大为原来的1.6倍（500 * 1.6 = 800）
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=-0.15,  # 缩小legend距离横轴的距离
                xanchor='center',
                x=0.5,
                font=dict(size=14)  # 增大图例文字大小
            )
        )
        
        # 生成HTML内容
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{symbol} 网格策略回测报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px 10px;
        }}
        .container {{
            max-width: 98vw;
            width: 100%;
            max-width: calc(100vw - 20px);
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 30px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #eee;
        }}
        .header h1 {{
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header p {{
            color: #666;
            font-size: 14px;
        }}
        .summary-card {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            transition: transform 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-5px);
        }}
        .card .label {{
            font-size: 12px;
            opacity: 0.9;
            margin-bottom: 5px;
        }}
        .card .value {{
            font-size: 24px;
            font-weight: bold;
        }}
        .chart-container {{
            background: #fafafa;
            border-radius: 12px;
            padding: 20px;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .chart-container > div {{
            width: 100% !important;
            max-width: 100%;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 12px;
        }}
        .instructions {{
            background: #e8f4fd;
            border-left: 4px solid #3498db;
            padding: 15px;
            margin-bottom: 30px;
            border-radius: 0 8px 8px 0;
        }}
        .instructions p {{
            color: #2980b9;
            font-size: 14px;
            line-height: 1.6;
        }}
    </style>
    <script charset="utf-8" src="https://cdn.plot.ly/plotly-3.1.0.min.js" integrity="sha256-Ei4740bWZhaUTQuD6q9yQlgVCMPBz6CZWhevDYPv93A=" crossorigin="anonymous"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 {symbol} 网格策略回测报告</h1>
            <p>使用 {self.results['grid_arbitrage_count']} 次网格套利，收益率 {self.results['return_rate']:.2f}%</p>
        </div>
        
        <div class="instructions">
            <p><strong>💡 交互说明：</strong>鼠标移动到曲线上可查看详细数据，支持缩放、平移和区域选择。</p>
        </div>
        
        <div class="summary-card">
            <div class="card">
                <div class="label">最终权益</div>
                <div class="value">${self.results['final_equity']:.2f}</div>
            </div>
            <div class="card">
                <div class="label">收益额</div>
                <div class="value">${self.results['total_pnl']:.2f}</div>
            </div>
            <div class="card">
                <div class="label">收益率</div>
                <div class="value">{self.results['return_rate']:.2f}%</div>
            </div>
            <div class="card">
                <div class="label">网格套利利润</div>
                <div class="value">${self.results['grid_arbitrage_pnl']:.2f}</div>
            </div>
            <div class="card">
                <div class="label">网格套利次数</div>
                <div class="value">{self.results['grid_arbitrage_count']}</div>
            </div>
            <div class="card">
                <div class="label">网格套利年化收益率</div>
                <div class="value">{self.results['grid_annualized_return']:.2f}%</div>
            </div>
            <div class="card">
                <div class="label">最大回撤</div>
                <div class="value">{self.results['max_drawdown']:.2%}</div>
            </div>
        </div>
        
        <div class="chart-container">
            {fig1.to_html(full_html=False, include_plotlyjs=False)}
        </div>
        
        <div class="chart-container" style="margin-top: 30px;">
            {fig2.to_html(full_html=False, include_plotlyjs=False)}
        </div>
        
        <div class="footer">
            <p>网格策略回测系统 © 2024 | 数据仅供参考，不构成投资建议</p>
        </div>
    </div>
</body>
</html>"""
        
        # 保存HTML文件
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f'{file_name}.html')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"HTML报告已保存到: {filepath}")
        return filepath
    
    def plot_equity_curve(self):
        """绘制权益曲线"""
        fig = go.Figure()
        df = pd.DataFrame(self.results['equity_curve'])
        
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['equity'],
            mode='lines',
            name='权益',
            hovertemplate='时间: %{x}<br>权益: $%{y:.2f}'
        ))
        
        fig.update_layout(
            title='权益变化曲线',
            xaxis_title='时间',
            yaxis_title='权益 (USDT)',
            hovermode='x unified',
            height=500
        )
        
        return fig
    
    def plot_pnl_curve(self):
        """绘制收益曲线"""
        fig = go.Figure()
        df = pd.DataFrame(self.results['pnl_curve'])
        
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['pnl'],
            mode='lines',
            name='收益',
            hovertemplate='时间: %{x}<br>收益: $%{y:.2f}'
        ))
        
        fig.update_layout(
            title='收益变化曲线',
            xaxis_title='时间',
            yaxis_title='收益 (USDT)',
            hovermode='x unified',
            height=500
        )
        
        return fig
    
    def plot_return_rate(self):
        """绘制收益率曲线（合并收益额显示）"""
        initial_margin = self.results['initial_margin']
        
        # 获取权益数据
        equity_df = pd.DataFrame(self.results['equity_curve'])
        equity_df['return_rate'] = ((equity_df['equity'] - initial_margin) / initial_margin) * 100
        
        # 获取收益数据
        pnl_df = pd.DataFrame(self.results['pnl_curve'])
        
        # 合并数据
        df = equity_df.merge(pnl_df, on='timestamp', how='left')
        df['pnl'] = df['pnl'].fillna(method='ffill')
        
        fig = go.Figure()
        
        # 只显示收益率曲线，但hover时显示收益率和收益额
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['return_rate'],
            mode='lines',
            name='收益率',
            hovertemplate='时间: %{x}<br>收益率: %{y:.2f}%<br>收益额: $%{customdata:.2f}',
            customdata=df['pnl']
        ))
        
        # 计算纵轴范围（增大显示范围）
        if not df['return_rate'].empty:
            min_rate = df['return_rate'].min()
            max_rate = df['return_rate'].max()
            # 增大显示范围，上下各留20%余量
            range_padding = (max_rate - min_rate) * 0.2 if (max_rate - min_rate) != 0 else 10
            y_min = min_rate - range_padding
            y_max = max_rate + range_padding
        else:
            y_min = -20
            y_max = 20
        
        fig.update_layout(
            title='收益率变化曲线',
            xaxis_title='时间',
            yaxis_title='收益率 (%)',
            yaxis_range=[y_min, y_max],
            hovermode='x unified',
            height=500
        )
        
        return fig
    
    def plot_arbitrage_count(self):
        """绘制网格套利次数曲线"""
        fig = go.Figure()
        df = pd.DataFrame(self.results['arbitrage_count_curve'])
        
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['count'],
            mode='lines',
            name='套利次数',
            hovertemplate='时间: %{x}<br>套利次数: %{y}'
        ))
        
        fig.update_layout(
            title='网格套利次数变化',
            xaxis_title='时间',
            yaxis_title='套利次数',
            hovermode='x unified',
            height=500
        )
        
        return fig
    
    def show_all_plots(self):
        """显示所有图表"""
        fig1 = self.plot_equity_curve()
        fig2 = self.plot_pnl_curve()
        fig3 = self.plot_return_rate()
        fig4 = self.plot_arbitrage_count()
        
        fig1.show()
        fig2.show()
        fig3.show()
        fig4.show()
    
    def plot_combined(self):
        """绘制组合图表"""
        initial_margin = self.results['initial_margin']
        
        # 将列表转换为DataFrame
        equity_df = pd.DataFrame(self.results['equity_curve'])
        pnl_df = pd.DataFrame(self.results['pnl_curve'])
        
        pnl_df['return_rate'] = (pnl_df['pnl'] / initial_margin) * 100
        
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=('权益变化', '收益变化', '收益率变化'),
            shared_xaxes=True,
            vertical_spacing=0.1
        )
        
        fig.add_trace(go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['equity'],
            mode='lines',
            name='权益'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=pnl_df['timestamp'],
            y=pnl_df['pnl'],
            mode='lines',
            name='收益',
            line=dict(color='green')
        ), row=2, col=1)
        
        fig.add_trace(go.Scatter(
            x=pnl_df['timestamp'],
            y=pnl_df['return_rate'],
            mode='lines',
            name='收益率',
            line=dict(color='orange')
        ), row=3, col=1)
        
        fig.update_layout(
            height=800,
            title_text='网格策略回测结果',
            hovermode='x unified'
        )
        
        fig.update_yaxes(title_text='权益 (USDT)', row=1, col=1)
        fig.update_yaxes(title_text='收益 (USDT)', row=2, col=1)
        fig.update_yaxes(title_text='收益率 (%)', row=3, col=1)
        fig.update_xaxes(title_text='时间', row=3, col=1)
        
        fig.show()
        return fig