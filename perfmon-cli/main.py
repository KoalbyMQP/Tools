#!/usr/bin/env python3

import psutil
import subprocess
import time
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
import signal
from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich.progress import Progress
import plotext as plt
from typing import Dict, List, Set, Optional
import yaml

class MetricsCollector:
    def __init__(self, config: dict):
        self.metrics = {
            'cpu_percent': [],
            'memory_percent': [],
            'memory_mb': [],
            'io_read_mb': [],
            'io_write_mb': [],
            'network_sent_mb': [],
            'network_recv_mb': [],
            'num_threads': [],
            'num_fds': [],
            'timestamps': []
        }
        self.start_time = None
        self.end_time = None
        self.config = config
        self.monitored_pids: Set[int] = set()

    def start_monitoring(self):
        self.start_time = datetime.now()
        if self.config.get('monitor_network', True):
            self.network_baseline = psutil.net_io_counters()

    def stop_monitoring(self):
        self.end_time = datetime.now()

    def _get_process_tree(self, pid: int) -> Set[int]:
        """Recursively get all child process IDs."""
        try:
            process = psutil.Process(pid)
            children = process.children(recursive=True)
            return {pid} | {child.pid for child in children}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return set()

    def collect_metrics(self, pid: int):
        """Collect metrics for a process and all its children."""
        self.monitored_pids = self._get_process_tree(pid)
        
        total_cpu = 0
        total_memory = 0
        total_memory_mb = 0
        total_io_read = 0
        total_io_write = 0
        total_net_sent = 0
        total_net_recv = 0
        total_threads = 0
        total_fds = 0

        for curr_pid in self.monitored_pids:
            try:
                process = psutil.Process(curr_pid)
                
                total_cpu += process.cpu_percent(interval=None)
                mem_info = process.memory_info()
                total_memory += process.memory_percent()
                total_memory_mb += mem_info.rss / 1024 / 1024

                io_counters = process.io_counters()
                total_io_read += io_counters.read_bytes / 1024 / 1024
                total_io_write += io_counters.write_bytes / 1024 / 1024

                total_threads += process.num_threads()
                if hasattr(process, 'num_fds'):
                    total_fds += process.num_fds()

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if self.config.get('monitor_network', True) and hasattr(self, 'network_baseline'):
            current_net = psutil.net_io_counters()
            total_net_sent = (current_net.bytes_sent - self.network_baseline.bytes_sent) / 1024 / 1024
            total_net_recv = (current_net.bytes_recv - self.network_baseline.bytes_recv) / 1024 / 1024
        else:
            total_net_sent = 0
            total_net_recv = 0

        self.metrics['timestamps'].append(time.time())
        self.metrics['cpu_percent'].append(total_cpu)
        self.metrics['memory_percent'].append(total_memory)
        self.metrics['memory_mb'].append(total_memory_mb)
        self.metrics['io_read_mb'].append(total_io_read)
        self.metrics['io_write_mb'].append(total_io_write)
        self.metrics['network_sent_mb'].append(total_net_sent)
        self.metrics['network_recv_mb'].append(total_net_recv)
        self.metrics['num_threads'].append(total_threads)
        self.metrics['num_fds'].append(total_fds)

    def get_summary(self) -> dict:
        """Generate a summary of the collected metrics."""
        duration = (self.end_time - self.start_time).total_seconds()
        
        return {
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'duration_seconds': duration,
            'avg_cpu_percent': sum(self.metrics['cpu_percent']) / len(self.metrics['cpu_percent']),
            'max_cpu_percent': max(self.metrics['cpu_percent']),
            'avg_memory_mb': sum(self.metrics['memory_mb']) / len(self.metrics['memory_mb']),
            'max_memory_mb': max(self.metrics['memory_mb']),
            'total_io_read_mb': self.metrics['io_read_mb'][-1],
            'total_io_write_mb': self.metrics['io_write_mb'][-1],
            'total_network_sent_mb': self.metrics['network_sent_mb'][-1],
            'total_network_recv_mb': self.metrics['network_recv_mb'][-1],
            'avg_threads': sum(self.metrics['num_threads']) / len(self.metrics['num_threads']),
            'avg_fds': sum(self.metrics['num_fds']) / len(self.metrics['num_fds'])
        }

class VisualOutput:
    def __init__(self, console: Console):
        self.console = console

    def create_live_table(self, metrics: dict) -> Table:
        """Create a rich table for live metrics display."""
        table = Table(title="Process Metrics")
        table.add_column("Metric")
        table.add_column("Value")

        table.add_row("CPU Usage", f"{metrics['cpu_percent'][-1]:.1f}%")
        table.add_row("Memory", f"{metrics['memory_mb'][-1]:.1f} MB")
        table.add_row("IO Read", f"{metrics['io_read_mb'][-1]:.1f} MB")
        table.add_row("IO Write", f"{metrics['io_write_mb'][-1]:.1f} MB")
        table.add_row("Network Sent", f"{metrics['network_sent_mb'][-1]:.1f} MB")
        table.add_row("Network Recv", f"{metrics['network_recv_mb'][-1]:.1f} MB")
        table.add_row("Threads", str(metrics['num_threads'][-1]))
        table.add_row("File Descriptors", str(metrics['num_fds'][-1]))

        return table

    def plot_metrics(self, metrics: dict, output_file: Optional[str] = None):
        """Create terminal-based plots of the metrics."""
        plt.clear_terminal()
        plt.clear_data()
        
        times = [t - metrics['timestamps'][0] for t in metrics['timestamps']]
        
        plt.plot(times, metrics['cpu_percent'], label="CPU %")
        plt.title("CPU Usage Over Time")
        plt.xlabel("Seconds")
        plt.ylabel("Percentage")
        if output_file:
            plt.savefig(f"{output_file}_cpu.png")
        plt.show()
        plt.clear_data()

        plt.plot(times, metrics['memory_mb'], label="Memory (MB)")
        plt.title("Memory Usage Over Time")
        plt.xlabel("Seconds")
        plt.ylabel("MB")
        if output_file:
            plt.savefig(f"{output_file}_memory.png")
        plt.show()

class PerfMon:
    def __init__(self, config_file: Optional[str] = None):
        self.console = Console()
        self.config = self._load_config(config_file)
        self.metrics_collector = MetricsCollector(self.config)
        self.visual_output = VisualOutput(self.console)
        self.sampling_interval = self.config.get('sampling_interval', 1.0)

    def _load_config(self, config_file: Optional[str]) -> dict:
        """Load configuration from file or use defaults."""
        default_config = {
            'sampling_interval': 1.0,
            'monitor_network': True,
            'export_formats': ['json'],
            'show_live_metrics': True,
            'create_plots': True
        }

        if config_file:
            try:
                with open(config_file, 'r') as f:
                    user_config = yaml.safe_load(f)
                default_config.update(user_config)
            except Exception as e:
                self.console.print(f"[yellow]Warning: Could not load config file: {e}")
                self.console.print("[yellow]Using default configuration")

        return default_config

    def run_command(self, command: List[str]):
        """Run and monitor the specified command."""
        try:
            process = subprocess.Popen(command)
            self.metrics_collector.start_monitoring()

            while process.poll() is None:
                self.metrics_collector.collect_metrics(process.pid)
                time.sleep(self.sampling_interval)

            self.metrics_collector.stop_monitoring()
            return_code = process.wait()

            self._generate_outputs()

            return return_code

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Monitoring interrupted by user")
            process.terminate()
            return 1

    def _generate_outputs(self):
        """Generate all configured output formats."""
        summary = self.metrics_collector.get_summary()
        
        if 'json' in self.config['export_formats']:
            self._export_json(summary)
        if 'csv' in self.config['export_formats']:
            self._export_csv()

        if self.config['create_plots']:
            self.visual_output.plot_metrics(self.metrics_collector.metrics)

    def _export_json(self, summary: dict):
        """Export metrics to JSON format."""
        output = {
            'summary': summary,
            'detailed_metrics': self.metrics_collector.metrics
        }
        
        with open('perfmon_results.json', 'w') as f:
            json.dump(output, f, indent=2)

    def _export_csv(self):
        """Export metrics to CSV format."""
        import pandas as pd
        
        df = pd.DataFrame(self.metrics_collector.metrics)
        df.to_csv('perfmon_results.csv', index=False)

def main():
    parser = argparse.ArgumentParser(description='Monitor performance metrics of a command')
    parser.add_argument('command', nargs='+', help='Command to execute and monitor')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--interval', type=float, help='Sampling interval in seconds')
    args = parser.parse_args()

    perfmon = PerfMon(args.config)
    if args.interval:
        perfmon.sampling_interval = args.interval

    return perfmon.run_command(args.command)

if __name__ == '__main__':
    sys.exit(main())