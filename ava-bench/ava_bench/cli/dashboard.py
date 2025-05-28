# ava_bench/cli/dashboard.py

from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.console import Group


def create_usage_bar(percent, width=20): return "█" * int(width * percent / 100) + "░" * (width - int(width * percent / 100))


class DashboardLayout:
    def __init__(self, console):
        self.console = console
        
        # Store dashboard data
        self.header_text = "AVA-Bench Dashboard"
        self.cpu_data = {}
        self.memory_data = {}  
        self.thermal_data = {}
        self.progress_data = {}
        self.results_data = {}
        self.footer_text = "Ready"
    
    def update_header(self, title="AVA-Bench Dashboard"):
        """Update header"""
        self.header_text = title
    
    def update_system_tiles(self, stats):
        """Update system monitoring data"""
        cpu = stats.get('cpu', {})
        memory = stats.get('memory', {})
        temps = stats.get('temperature', {})
        
        # Store data for rendering
        self.cpu_data = {
            'usage': cpu.get('usage_percent', 0) or 0,
            'freq': cpu.get('frequency_ghz', 0) or 0,
            'load': cpu.get('load_1min', 0) or 0,
            'cores': cpu.get('core_count', 4) or 0
        }
        
        self.memory_data = {
            'used': memory.get('ram_used_gb', 0) or 0,
            'total': memory.get('ram_total_gb', 8) or 0,
            'percent': memory.get('ram_percent', 0) or 0,
            'swap': memory.get('swap_used_gb', 0) or 0
        }
        
        cpu_temp = temps.get('cpu_temp', 0) or 0
        throttle = stats.get('throttling', {})
        is_throttled = throttle.get('is_throttled', False)
        
        self.thermal_data = {
            'temp': cpu_temp,
            'throttled': is_throttled,
            'color': "green" if cpu_temp < 60 else "yellow" if cpu_temp < 75 else "red",
            'status': "Cool" if cpu_temp < 60 else "Warm" if cpu_temp < 75 else "Hot"
        }
    
    def update_progress(self, current_stage, percent=0, past_stages=None, future_stages=None):
        """Update progress data"""
        self.progress_data = {
            'current': current_stage,
            'percent': percent,
            'past': past_stages or [],
            'future': future_stages or []
        }
    
    def update_results(self, results=None):
        """Update results data"""
        if not results:
            self.results_data = {'status': 'waiting'}
            return
            
        duration = results.get('duration_seconds', 0)
        throughput = results.get('ops_per_second', 0)
        
        if duration < 5 and throughput > 1000: status, color = "Excellent", "green"
        elif duration < 10: status, color = "Good", "bright_green"  
        elif duration < 30: status, color = "Fair", "yellow"
        else: status, color = "Poor", "red"
        
        self.results_data = {
            'duration': duration,
            'throughput': throughput,
            'status': status,
            'color': color
        }
    
    def update_footer(self, message="Ready"):
        """Update footer message"""
        self.footer_text = message
    
    def render(self):
        """Render dashboard as simple inline elements"""
        
        # Header
        header = Panel(Text(self.header_text, style="bold cyan", justify="center"), border_style="cyan")
        
        # System tiles row
        cpu_text = Text()
        cpu_text.append(f"CPU: {create_usage_bar(self.cpu_data.get('usage', 0))}\n", style="bright_blue")
        cpu_text.append(f"{self.cpu_data.get('usage', 0):.0f}%\n", style="bright_blue")
        cpu_text.append(f"Load: {self.cpu_data.get('load', 0):.1f}/{self.cpu_data.get('cores', 4)}\n", style="white")
        cpu_text.append(f"Freq: {self.cpu_data.get('freq', 0):.1f}GHz", style="dim white")
        cpu_tile = Panel(cpu_text, title="System", border_style="blue", width=25)
        
        memory_text = Text()
        memory_text.append(f"RAM: {create_usage_bar(self.memory_data.get('percent', 0))}\n", style="bright_green")
        memory_text.append(f"{self.memory_data.get('percent', 0):.0f}%\n", style="bright_green")
        memory_text.append(f"{self.memory_data.get('used', 0):.1f}GB / {self.memory_data.get('total', 8):.1f}GB\n", style="white")
        memory_text.append(f"Swap: {self.memory_data.get('swap', 0):.1f}GB", style="dim white")
        memory_tile = Panel(memory_text, title="Memory", border_style="green", width=25)
        
        thermal_color = self.thermal_data.get('color', 'white')
        thermal_text = Text()
        thermal_text.append(f"CPU: {self.thermal_data.get('temp', 0):.0f}C\n", style=thermal_color)
        thermal_text.append(f"Status: {self.thermal_data.get('status', 'Normal')}\n", style=thermal_color)
        thermal_text.append("Throttled\n" if self.thermal_data.get('throttled') else "Normal\n", style="red" if self.thermal_data.get('throttled') else "white")
        thermal_text.append("Stable", style="dim white")
        thermal_tile = Panel(thermal_text, title="Thermal", border_style=thermal_color, width=25)
        
        system_row = Columns([cpu_tile, memory_tile, thermal_tile], equal=True)
        
        # Progress row
        progress_text = Text()
        if self.progress_data.get('past'):
            past_str = " -> ".join(self.progress_data['past'][-2:])
            progress_text.append(f"Past: {past_str}\n", style="dim white")
        
        current = self.progress_data.get('current', 'waiting')
        percent = self.progress_data.get('percent', 0)
        progress_bar = create_usage_bar(percent, 30)
        progress_text.append(f"Current: {current}\n", style="bold bright_cyan")
        progress_text.append(f"{progress_bar} {percent:.0f}%\n", style="bright_cyan")
        
        if self.progress_data.get('future'):
            future_str = " -> ".join(self.progress_data['future'][:2])
            progress_text.append(f"Next: {future_str}", style="dim cyan")
        
        progress_panel = Panel(progress_text, title="Progress", border_style="cyan")
        
        # Results row
        if self.results_data.get('status') == 'waiting':
            results_text = Text("Waiting for results...", style="dim white")
            results_panel = Panel(results_text, title="Results", border_style="white")
        else:
            results_text = Text()
            results_text.append(f"Duration: {self.results_data.get('duration', 0):.3f}s  |  ", style="white")
            results_text.append(f"Throughput: {self.results_data.get('throughput', 0):,.0f} ops/sec  |  ", style="white")
            results_text.append(f"Status: {self.results_data.get('status', 'Unknown')}", style=self.results_data.get('color', 'white'))
            results_panel = Panel(results_text, title="Live Results", border_style=self.results_data.get('color', 'white'))
        
        footer = Panel(Text(self.footer_text, style="bright_white", justify="center"), border_style="white")
        
        # Group everything together for inline rendering
        return Group(header, system_row, progress_panel, results_panel, footer)
