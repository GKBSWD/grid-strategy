import requests
import pandas as pd
import os
from datetime import datetime, timedelta
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pyarrow as pa
import pyarrow.parquet as pq

class KlineData:
    def __init__(self, data_dir='data', log_callback=None, stop_callback=None):
        self.data_dir = data_dir
        self.max_retries = 2  # 每个数据源尝试2次
        self.retry_delay = 2
        self.max_workers = 8  # 最大线程数
        self.memory_cache = {}  # 内存缓存
        self.log_callback = log_callback  # 日志回调函数
        self.stop_callback = stop_callback  # 停止回调函数
        self._log_lock = threading.Lock()  # 线程锁，确保日志输出的线程安全
        
        # 定义交易所的API限制
        self.api_limits = {
            'Binance': {'limit': 1000, 'max_hours_per_request': 42}
        }
        
        self.data_sources = [
            {'name': 'Binance', 'func': self.get_kline_from_binance_batch, 'priority': 1},
        ]
        
        # 支持的快速文件格式
        self.fast_formats = ['parquet', 'feather']
        
    def _log(self, message):
        """日志输出，支持回调函数（线程安全）"""
        with self._log_lock:
            print(message)
            if self.log_callback:
                self.log_callback(message)
    
    def _check_stop(self):
        """检查是否需要停止（返回 True 时应停止）"""
        if self.stop_callback:
            try:
                return self.stop_callback()
            except:
                return False
        return False
    
    def _calculate_request_interval(self, source_name, bar):
        """计算每次请求的时间间隔（考虑API限制）"""
        limit_info = self.api_limits.get(source_name, {'limit': 1000, 'max_hours_per_request': 24})
        minutes_per_bar = self._get_minutes_from_bar(bar)
        
        max_minutes = min(
            limit_info['limit'] * minutes_per_bar,
            limit_info['max_hours_per_request'] * 60
        )
        
        return timedelta(minutes=max_minutes)
    
    def _get_minutes_from_bar(self, bar):
        """将bar周期转换为分钟数"""
        mapping = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440}
        return mapping.get(bar, 5)
    
    def _fetch_binance_batch(self, symbol, start_time, end_time, interval, request_id):
        """获取单个批次的Binance K线数据"""
        params = {
            'symbol': f'{symbol}USDT',
            'interval': interval,
            'limit': 1000,
            'startTime': int(start_time.timestamp() * 1000),
            'endTime': int(end_time.timestamp() * 1000)
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.get('https://fapi.binance.com/fapi/v1/klines', params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                klines = []
                for candle in data:
                    ts = datetime.fromtimestamp(int(candle[0]) / 1000)
                    klines.append({
                        'timestamp': ts,
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': float(candle[5])
                    })
                
                self._log(f"   线程{request_id}: 获取 {len(klines)} 条K线 [{start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}]")
                return klines
                
            except Exception as e:
                self._log(f"   线程{request_id}: Binance请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
        
        self._log(f"   线程{request_id}: Binance获取失败")
        return []
    
    def get_kline_from_binance_batch(self, symbol, start_time, end_time, bar='5m'):
        """使用多线程从Binance获取K线数据"""
        klines = []
        bar_mapping = {'1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h', '4h': '4h', '1d': '1d'}
        interval = bar_mapping.get(bar, '5m')
        
        request_interval = self._calculate_request_interval('Binance', bar)
        total_requests = int((end_time - start_time).total_seconds() / request_interval.total_seconds()) + 1
        
        self._log(f"📥 正在从Binance获取 {symbol} 数据...")
        self._log(f"   时间范围: {start_time.strftime('%Y-%m-%d %H:%M')} 到 {end_time.strftime('%Y-%m-%d %H:%M')}")
        self._log(f"   预计需要 {total_requests} 次请求")
        self._log(f"   使用 {min(self.max_workers, total_requests)} 个线程并行获取")
        
        # 生成所有请求任务
        tasks = []
        current_start = start_time
        request_id = 0
        
        while current_start < end_time:
            batch_end = min(current_start + request_interval, end_time)
            tasks.append((request_id, current_start, batch_end))
            current_start = batch_end
            request_id += 1
        
        # 使用多线程并行获取
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for req_id, batch_start, batch_end in tasks:
                # 停止检查点
                if self._check_stop():
                    self._log(f"⏹ 数据获取被停止，已跳过剩余请求")
                    break
                future = executor.submit(
                    self._fetch_binance_batch,
                    symbol, batch_start, batch_end, interval, req_id
                )
                futures[future] = (req_id, batch_start)
            
            # 收集结果（按请求顺序）
            for future in as_completed(futures):
                # 停止检查点
                if self._check_stop():
                    self._log(f"⏹ 数据获取被停止，已跳过剩余结果")
                    break
                req_id, batch_start = futures[future]
                try:
                    result = future.result()
                    results.append((batch_start, result))
                except Exception as e:
                    self._log(f"   线程{req_id}: 处理结果时出错: {e}")
        
        # 按时间顺序合并结果
        results.sort(key=lambda x: x[0])
        for _, batch_klines in results:
            klines.extend(batch_klines)
        
        # 转换为DataFrame并去重排序
        df = pd.DataFrame(klines)
        if not df.empty:
            df = df.sort_values('timestamp').drop_duplicates('timestamp')
            self._log(f"✓ Binance获取完成，共获取 {len(df)} 条K线")
        
        return df
    
    def _print_progress(self, progress, fetched, total):
        """打印进度条"""
        bar_length = 40
        filled_length = int(bar_length * progress / 100)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"\r进度: [{bar}] {progress}% ({fetched}/{total}分钟)", end='', flush=True)
    
    def _get_file_paths(self, symbol, bar):
        """获取所有可能的文件路径"""
        paths = {}
        
        # Parquet格式（高效存储）
        for fmt in self.fast_formats:
            paths[fmt] = os.path.join(self.data_dir, f'{symbol}_{bar}_klines.{fmt}')
        
        return paths
    
    def save_kline_to_excel(self, df, symbol, bar):
        """保存K线数据到Excel（兼容旧版本）"""
        os.makedirs(self.data_dir, exist_ok=True)
        filename = f'{symbol}_{bar}_klines.xlsx'
        filepath = os.path.join(self.data_dir, filename)
        df.to_excel(filepath, index=False)
        print(f"K线数据已保存到Excel: {filepath}")
        return filepath
    
    def _format_time_for_filename(self, dt):
        """格式化时间用于文件名"""
        return dt.strftime('%Y%m%d_%H%M%S')
    
    def _parse_time_from_filename(self, time_str):
        """从文件名解析时间"""
        try:
            return datetime.strptime(time_str, '%Y%m%d_%H%M%S')
        except:
            return None
    
    def _delete_old_data_files(self, symbol, bar, fmt='parquet'):
        """删除同标的同周期的旧数据文件"""
        import glob
        
        # 删除旧格式文件: {symbol}_{bar}_klines.parquet
        old_pattern = os.path.join(self.data_dir, f'{symbol}_{bar}_klines.{fmt}')
        for filepath in glob.glob(old_pattern):
            try:
                os.remove(filepath)
                print(f"删除旧格式文件: {filepath}")
            except Exception as e:
                print(f"删除文件失败 {filepath}: {e}")
        
        # 删除新格式文件: {symbol}_{bar}_{start}_{end}.parquet
        new_pattern = os.path.join(self.data_dir, f'{symbol}_{bar}_*_*.{fmt}')
        for filepath in glob.glob(new_pattern):
            try:
                os.remove(filepath)
                print(f"删除旧数据文件: {filepath}")
            except Exception as e:
                print(f"删除文件失败 {filepath}: {e}")
    
    def save_kline_to_fast_format(self, df, symbol, bar, fmt='parquet'):
        """保存K线数据到快速格式（Parquet/Feather）"""
        if fmt not in self.fast_formats:
            print(f"不支持的格式: {fmt}")
            return None
        
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 获取数据的时间范围
        df_start = df['timestamp'].min()
        df_end = df['timestamp'].max()
        
        # 删除同标的同周期的旧数据文件，确保只有一份时间跨度最长的数据文件
        self._delete_old_data_files(symbol, bar, fmt)
        
        # 新的文件名格式: {symbol}_{bar}_{start_time}_{end_time}.parquet
        filename = f'{symbol}_{bar}_{self._format_time_for_filename(df_start)}_{self._format_time_for_filename(df_end)}.{fmt}'
        filepath = os.path.join(self.data_dir, filename)
        
        try:
            if fmt == 'parquet':
                df.to_parquet(filepath, index=False)
            elif fmt == 'feather':
                df.to_feather(filepath)
            print(f"K线数据已保存到{fmt.upper()}格式: {filepath}")
            return filepath
        except Exception as e:
            print(f"保存到{fmt.upper()}格式失败: {e}")
            return None
    
    def load_kline_from_excel(self, symbol, bar):
        """从Excel加载K线数据（单文件）"""
        filepath = os.path.join(self.data_dir, f'{symbol}_{bar}_klines.xlsx')
        
        if os.path.exists(filepath):
            try:
                start_time = time.time()
                # 使用openpyxl引擎（支持xlsx格式，通常更快）
                df = pd.read_excel(filepath, engine='openpyxl')
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                load_time = time.time() - start_time
                print(f"从Excel加载完成，耗时 {load_time:.2f} 秒，共 {len(df)} 条数据")
                return df
            except Exception as e:
                print(f"加载Excel文件失败: {e}")
                return None
        return None
    
    def load_kline_from_fast_format(self, symbol, bar, fmt='parquet'):
        """从快速格式加载K线数据"""
        if fmt not in self.fast_formats:
            print(f"不支持的格式: {fmt}")
            return None
        
        filepath = os.path.join(self.data_dir, f'{symbol}_{bar}_klines.{fmt}')
        
        if os.path.exists(filepath):
            try:
                start_time = time.time()
                if fmt == 'parquet':
                    table = pq.read_table(filepath)
                    df = table.to_pandas()
                elif fmt == 'feather':
                    df = pd.read_feather(filepath)
                
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                load_time = time.time() - start_time
                print(f"从{fmt.upper()}格式加载完成，耗时 {load_time:.2f} 秒，共 {len(df)} 条数据")
                return df
            except Exception as e:
                print(f"加载{fmt.upper()}格式失败: {e}")
                return None
        return None
    
    def _load_single_file(self, filepath, file_type):
        """加载单个文件（用于多文件并行读取）"""
        try:
            if file_type == 'parquet':
                table = pq.read_table(filepath)
                df = table.to_pandas()
            elif file_type == 'feather':
                df = pd.read_feather(filepath)
            else:
                return None
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            print(f"加载文件 {filepath} 失败: {e}")
            return None
    
    def load_kline_from_multiple_files(self, symbol, bar, parallel=True):
        """
        从多个文件并行加载K线数据
        
        如果数据被拆分成多个文件（如按日期拆分），可以使用此方法并行加载
        文件命名格式: {symbol}_{bar}_klines_YYYYMMDD.xlsx/.parquet/.feather
        """
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 查找所有匹配的文件
        import glob
        file_patterns = [
            f'{symbol}_{bar}_klines_*.parquet',
            f'{symbol}_{bar}_klines_*.feather'
        ]
        
        all_files = []
        for pattern in file_patterns:
            all_files.extend(glob.glob(os.path.join(self.data_dir, pattern)))
        
        if not all_files:
            print("未找到拆分的数据文件")
            return None
        
        print(f"发现 {len(all_files)} 个拆分数据文件")
        
        start_time = time.time()
        
        if parallel and len(all_files) > 1:
            # 使用多线程并行加载
            print(f"使用 {min(self.max_workers, len(all_files))} 个线程并行加载...")
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                
                for filepath in all_files:
                    file_ext = filepath.split('.')[-1].lower()
                    file_type = file_ext
                    future = executor.submit(self._load_single_file, filepath, file_type)
                    futures.append(future)
                
                # 收集结果
                dfs = []
                for future in as_completed(futures):
                    df = future.result()
                    if df is not None:
                        dfs.append(df)
        else:
            # 顺序加载
            dfs = []
            for filepath in sorted(all_files):
                file_ext = filepath.split('.')[-1].lower()
                file_type = file_ext
                df = self._load_single_file(filepath, file_type)
                if df is not None:
                    dfs.append(df)
        
        if dfs:
            # 合并所有数据
            df = pd.concat(dfs, ignore_index=True)
            df = df.sort_values('timestamp').drop_duplicates('timestamp')
            load_time = time.time() - start_time
            print(f"多文件加载完成，耗时 {load_time:.2f} 秒，共 {len(df)} 条数据")
            return df
        
        return None
    
    def load_kline_with_cache(self, symbol, bar, use_cache=True):
        """
        带内存缓存的K线数据加载
        
        :param symbol: 交易品种
        :param bar: K线周期
        :param use_cache: 是否使用内存缓存
        :return: DataFrame或None
        """
        cache_key = f'{symbol}_{bar}'
        
        # 检查内存缓存
        if use_cache and cache_key in self.memory_cache:
            print(f"使用内存缓存加载数据")
            return self.memory_cache[cache_key]
        
        # 优先尝试快速格式
        for fmt in self.fast_formats:
            df = self.load_kline_from_fast_format(symbol, bar, fmt)
            if df is not None:
                if use_cache:
                    self.memory_cache[cache_key] = df
                return df
        
        # 尝试多文件加载
        df = self.load_kline_from_multiple_files(symbol, bar)
        if df is not None:
            if use_cache:
                self.memory_cache[cache_key] = df
            return df
        
        return df
    
    def clear_cache(self):
        """清空内存缓存"""
        self.memory_cache.clear()
        print("内存缓存已清空")
    
    def convert_to_fast_format(self, symbol, bar, fmt='parquet'):
        """将Excel数据转换为快速格式"""
        df = self.load_kline_from_excel(symbol, bar)
        if df is not None:
            return self.save_kline_to_fast_format(df, symbol, bar, fmt)
        return None
    
    def find_existing_data_range(self, symbol, bar):
        """查找现有的数据文件，返回覆盖的时间范围和文件列表"""
        import glob
        
        all_dfs = []
        all_files = []
        
        for fmt in self.fast_formats:
            # 新格式: {symbol}_{bar}_{start}_{end}.parquet
            pattern = os.path.join(self.data_dir, f'{symbol}_{bar}_*_*.{fmt}')
            files = glob.glob(pattern)
            
            for filepath in files:
                try:
                    if fmt == 'parquet':
                        df = pd.read_parquet(filepath)
                    else:
                        df = pd.read_feather(filepath)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    all_dfs.append(df)
                    all_files.append(filepath)
                except Exception as e:
                    print(f"读取文件失败 {filepath}: {e}")
        
        if not all_dfs:
            return None, None, None  # 没有找到数据
        
        # 合并所有数据
        combined_df = pd.concat(all_dfs, ignore_index=True)
        combined_df = combined_df.sort_values('timestamp').drop_duplicates('timestamp')
        
        data_start = combined_df['timestamp'].min()
        data_end = combined_df['timestamp'].max()
        
        return combined_df, data_start, data_end
    
    def is_data_valid(self, symbol, bar, start_time, end_time):
        """检查已保存的数据是否满足回测需求"""
        df, data_start, data_end = self.find_existing_data_range(symbol, bar)
        
        if df is None:
            print(f"未找到有效的{self.fast_formats}格式数据")
            return False, None, None, None
        
        # 检查是否完全覆盖需求时间范围
        fully_covered = data_start <= start_time and data_end >= end_time
        
        if fully_covered:
            print(f"已保存的数据有效: 覆盖时间范围 [{data_start.strftime('%Y-%m-%d %H:%M')} - {data_end.strftime('%Y-%m-%d %H:%M')}]")
            return True, 'parquet', df, None
        else:
            # 计算缺失的时间范围
            missing_before = None
            missing_after = None
            
            if data_start > start_time:
                missing_before = (start_time, data_start)
                print(f"需要补充历史数据: [{start_time.strftime('%Y-%m-%d %H:%M')} - {data_start.strftime('%Y-%m-%d %H:%M')}]")
            
            if data_end < end_time:
                missing_after = (data_end, end_time)
                print(f"需要补充最新数据: [{data_end.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}]")
            
            return False, 'parquet', df, {'before': missing_before, 'after': missing_after}
    
    def _fetch_data_from_sources(self, symbol, fetch_start, fetch_end, bar):
        """从数据源获取指定时间范围的数据"""
        total_minutes = int((fetch_end - fetch_start).total_seconds() / 60)
        fetched_minutes = 0
        all_klines = []
        
        sorted_sources = sorted(self.data_sources, key=lambda x: x['priority'])
        
        for source in sorted_sources:
            self._log(f"\n🌐 尝试数据源: {source['name']}")
            self._log(f"   API地址: https://fapi.binance.com/fapi/v1/klines")
            df = source['func'](symbol, fetch_start, fetch_end, bar)
            
            if not df.empty:
                all_klines.extend(df.to_dict('records'))
                fetched_minutes += len(df) * self._get_minutes_from_bar(bar)
                progress = min(100, int(fetched_minutes / total_minutes * 100))
                self._print_progress(progress, fetched_minutes, total_minutes)
                
                if fetched_minutes >= total_minutes:
                    break
        
        if all_klines:
            df = pd.DataFrame(all_klines)
            df = df.sort_values('timestamp').drop_duplicates('timestamp')
            return df
        return None
    
    def get_kline_data(self, symbol, start_time, end_time, bar='5m', prefer_fast_format=True):
        """
        获取K线数据，支持增量更新
        
        :param symbol: 交易品种
        :param start_time: 起始时间
        :param end_time: 结束时间
        :param bar: K线周期
        :param prefer_fast_format: 是否优先使用快速格式
        :return: DataFrame
        """
        # 检查是否有有效的本地数据
        valid, fmt, existing_df, missing_info = self.is_data_valid(symbol, bar, start_time, end_time)
        
        if valid:
            self._log(f"✓ 使用已保存的数据")
            return existing_df[(existing_df['timestamp'] >= start_time) & (existing_df['timestamp'] <= end_time)]
        
        # 需要增量更新或完全新获取
        if existing_df is not None and missing_info is not None:
            # 增量更新模式
            self._log(f"🔄 执行增量数据更新...")
            
            all_dfs = [existing_df]
            
            # 获取缺失的历史数据（如果需要）
            if missing_info['before']:
                fetch_start, fetch_end = missing_info['before']
                self._log(f"📥 获取历史数据: [{fetch_start.strftime('%Y-%m-%d %H:%M')} - {fetch_end.strftime('%Y-%m-%d %H:%M')}]")
                new_df = self._fetch_data_from_sources(symbol, fetch_start, fetch_end, bar)
                if new_df is not None:
                    all_dfs.append(new_df)
            
            # 获取缺失的最新数据（如果需要）
            if missing_info['after']:
                fetch_start, fetch_end = missing_info['after']
                self._log(f"📥 获取最新数据: [{fetch_start.strftime('%Y-%m-%d %H:%M')} - {fetch_end.strftime('%Y-%m-%d %H:%M')}]")
                new_df = self._fetch_data_from_sources(symbol, fetch_start, fetch_end, bar)
                if new_df is not None:
                    all_dfs.append(new_df)
            
            # 合并所有数据
            final_df = pd.concat(all_dfs, ignore_index=True)
            final_df = final_df.sort_values('timestamp').drop_duplicates('timestamp')
            
            self._log(f"\n✓ 增量更新完成，共 {len(final_df)} 条K线")
            
            # 保存合并后的数据
            self.save_kline_to_fast_format(final_df, symbol, bar, 'parquet')
            
            return final_df[(final_df['timestamp'] >= start_time) & (final_df['timestamp'] <= end_time)]
        else:
            # 完全新获取模式
            self._log(f"🔄 完全获取新数据...")
            total_minutes = int((end_time - start_time).total_seconds() / 60)
            fetched_minutes = 0
            all_klines = []
            
            sorted_sources = sorted(self.data_sources, key=lambda x: x['priority'])
            
            for source in sorted_sources:
                self._log(f"\n🌐 尝试数据源: {source['name']}")
                self._log(f"   API地址: https://fapi.binance.com/fapi/v1/klines")
                df = source['func'](symbol, start_time, end_time, bar)
                
                if not df.empty:
                    all_klines.extend(df.to_dict('records'))
                    fetched_minutes += len(df) * self._get_minutes_from_bar(bar)
                    progress = min(100, int(fetched_minutes / total_minutes * 100))
                    self._print_progress(progress, fetched_minutes, total_minutes)
                    
                    if fetched_minutes >= total_minutes:
                        break
            
            final_df = pd.DataFrame(all_klines)
            if not final_df.empty:
                final_df = final_df.sort_values('timestamp').drop_duplicates('timestamp')
                self._log(f"\n✓ 数据获取完成，共获取 {len(final_df)} 条K线")
                
                # 保存到Parquet格式（高效存储）
                self.save_kline_to_fast_format(final_df, symbol, bar, 'parquet')
                
                return final_df[(final_df['timestamp'] >= start_time) & (final_df['timestamp'] <= end_time)]
            else:
                self._log("\n❌ 所有数据源都获取失败")
                return pd.DataFrame()