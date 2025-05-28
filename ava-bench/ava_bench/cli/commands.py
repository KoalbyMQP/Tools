# ava_bench/cli/commands.py

import time
import click

from ..core.orchestrator import Orchestrator
from ..core.sweep import SweepConfig, Sweep
from ..hardware.monitor import SystemMonitor
from .dashboard import DashboardLayout
from .display import display_error, display_success


@click.command()
@click.argument('benchmark_id')
@click.option('--iterations', '-i', default=1000, help='Number of iterations')
@click.option('--output', '-o', type=click.Path(), help='Output file for results')
@click.option('--monitor/--no-monitor', default=True, help='Show live dashboard')
@click.pass_context
def run(ctx, benchmark_id, iterations, output, monitor):    
    console = ctx.obj['console']
    quiet = ctx.obj['quiet']
    
    if quiet:
        orch = Orchestrator()
        bench = orch.create_benchmark(benchmark_id, {"iterations": iterations})
        if bench.initialize():
            result = bench.test()
            bench.cleanup()
            if output: _save_result(result, output, console, quiet)
        return
    
    # Dashboard mode
    system_monitor = SystemMonitor()
    dashboard = DashboardLayout(console)
    
    try:
        # Setup benchmark
        orch = Orchestrator()
        config = {"iterations": iterations}
        bench = orch.create_benchmark(benchmark_id, config)
        
        if not bench.initialize():
            display_error(console, f"Failed to initialize benchmark: {benchmark_id}")
            ctx.exit(1)
        
        if monitor:
            result = _run_with_inline_dashboard(console, bench, benchmark_id, system_monitor, dashboard)
        else:
            result = bench.test()
        
        bench.cleanup()
        
        # Final success message
        display_success(console, f"Benchmark '{benchmark_id}' completed successfully!")
        
        if output: _save_result(result, output, console, quiet)
        
    except Exception as e:
        display_error(console, f"Benchmark failed: {str(e)}")
        ctx.exit(1)


@click.command()
@click.argument('config_path', type=click.Path(exists=True))
@click.option('--name', '-n', help='Name for this sweep run')
@click.option('--output-dir', '-o', type=click.Path(), help='Output directory for results')
@click.option('--monitor/--no-monitor', default=True, help='Show live dashboard')
@click.pass_context
def sweep(ctx, config_path, name, output_dir, monitor):    
    console = ctx.obj['console']
    quiet = ctx.obj['quiet']
    
    if quiet:
        orch = Orchestrator()
        config = SweepConfig.load(config_path)
        sweep_runner = Sweep(orch)
        results = sweep_runner.run(config_path)
        if output_dir: _save_sweep_results(results, output_dir, name, console, quiet)
        return
    
    console.print(f"[info]Loading sweep config: [benchmark]{config_path}[/benchmark][/info]")
    
    # Initialize system monitor and dashboard
    system_monitor = SystemMonitor()
    dashboard = DashboardLayout(console)
    
    try:
        # Load and validate config
        config = SweepConfig.load(config_path)
        combinations = config.generate_combinations()
        
        console.print(f"[info]Generated [metric]{len(combinations)}[/metric] benchmark combinations[/info]")
        stats = system_monitor.get_all_stats()
        console.print(f"[info]Running on: [benchmark]{stats['pi_model']}[/benchmark][/info]")
        console.print()
        
        # Setup sweep
        orch = Orchestrator()
        sweep_runner = Sweep(orch)
        
        if monitor:
            results = _run_sweep_with_inline_dashboard(console, sweep_runner, config_path, combinations, system_monitor, dashboard, name or "sweep")
        else:
            results = sweep_runner.run(config_path)
        
        # Display final results table (after dashboard)
        display_success(console, f"Sweep completed! {len(results)} benchmarks executed.")
        
        # Save results if requested
        if output_dir:
            _save_sweep_results(results, output_dir, name, console, quiet)
            
    except Exception as e:
        display_error(console, f"Sweep failed: {str(e)}")
        ctx.exit(1)

def _run_with_inline_dashboard(console, bench, benchmark_id, system_monitor, dashboard):
    """Run benchmark with inline dashboard that refreshes in place"""
    from rich.live import Live
    
    # Dashboard stages
    stages = ["initializing", "loading", "computing", "finalizing", "complete"]
    
    # Initial dashboard setup
    dashboard.update_header(f"Running: {benchmark_id}")
    dashboard.update_system_tiles(system_monitor.get_all_stats())
    dashboard.update_progress(stages[0], 0, [], stages[1:])
    dashboard.update_results()
    dashboard.update_footer("Starting benchmark...")
    
    # Use Live with transient=True for inline refresh
    with Live(dashboard.render(), refresh_per_second=2, console=console, transient=True) as live:
        
        # Progress updates
        update_points = [20, 40, 60, 80, 100]
        for progress_percent in update_points:
            time.sleep(0.2)  # Brief pause
            
            # Calculate current stage
            stage_progress = progress_percent / 100 * len(stages)
            current_stage_idx = min(int(stage_progress), len(stages) - 1)
            current_stage = stages[current_stage_idx]
            past_stages = stages[:current_stage_idx] if current_stage_idx > 0 else []
            future_stages = stages[current_stage_idx + 1:] if current_stage_idx < len(stages) - 1 else []
            
            # Update dashboard
            dashboard.update_system_tiles(system_monitor.get_all_stats())
            dashboard.update_progress(current_stage, progress_percent, past_stages, future_stages)
            dashboard.update_footer(f"Progress: {progress_percent}% - {current_stage}")
            
            # Live will automatically refresh
            live.update(dashboard.render())
        
        # Run actual benchmark
        result = bench.test()
        
        # Final update
        dashboard.update_progress("complete", 100, stages[:-1], [])
        dashboard.update_results(result)
        dashboard.update_footer("Benchmark completed!")
        live.update(dashboard.render())
        
        time.sleep(1)  # Show final state briefly
    
    # After Live exits, the final dashboard stays visible
    return result


def _run_sweep_with_inline_dashboard(console, sweep_runner, config_path, combinations, system_monitor, dashboard, sweep_name):
    """Run sweep with inline dashboard that refreshes in place"""
    from rich.live import Live
    
    # Initial dashboard setup
    dashboard.update_header(f"Sweep: {sweep_name}")
    dashboard.update_system_tiles(system_monitor.get_all_stats())
    dashboard.update_progress("starting", 0, [], ["loading", "executing", "finishing"])
    dashboard.update_results()
    dashboard.update_footer(f"Starting sweep with {len(combinations)} benchmarks...")
    
    # Use Live with transient=True for inline refresh
    with Live(dashboard.render(), refresh_per_second=2, console=console, transient=True) as live:
        
        # Sweep progress updates
        total_benchmarks = len(combinations)
        update_interval = max(1, total_benchmarks // 5)  # 5 updates max
        
        for i in range(0, total_benchmarks, update_interval):
            progress_percent = int((i / total_benchmarks) * 100)
            
            # Update dashboard
            dashboard.update_system_tiles(system_monitor.get_all_stats())
            dashboard.update_progress("executing", progress_percent, ["starting"], ["finishing"])
            dashboard.update_footer(f"Running benchmark {i+1}/{total_benchmarks}...")
            
            live.update(dashboard.render())
            time.sleep(0.3)  # Brief pause
        
        results = sweep_runner.run(config_path)
        
        dashboard.update_progress("complete", 100, ["starting", "executing"], [])
        dashboard.update_footer(f"Completed {len(results)} benchmarks!")
        live.update(dashboard.render())
        
        time.sleep(1)
    
    return results


def _save_result(result, output_path, console, quiet):
    """Save benchmark result"""
    import json
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    if not quiet:
        console.print(f"Results saved to: {output_path}")


def _save_sweep_results(results, output_dir, name, console, quiet):
    """Save sweep results"""
    import json
    from pathlib import Path
    
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    filename = f"{name or 'sweep'}_results.json"
    output_path = output_dir / filename
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    if not quiet:
        console.print(f"Sweep results saved to: {output_path}")