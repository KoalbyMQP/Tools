# ava_bench/cli/commands.py

import time
import click

from ..core.orchestrator import Orchestrator
from ..core.sweep import SweepConfig, Sweep
from ..monitoring import create_monitor
from .dashboard import DashboardLayout
from .display import display_error, display_success


@click.command()
@click.argument('benchmark_id')
@click.option('--iterations', '-i', default=1000, help='Number of iterations')
@click.option('--output', '-o', type=click.Path(), help='Output file for results')
@click.option('--monitor/--no-monitor', default=True, help='Show live dashboard')
@click.option('--visual/--no-visual', default=False, help='Enable real-time performance plots')  # NEW
@click.option('--save-monitoring', type=click.Path(), help='Save monitoring data to file')
@click.pass_context
def run(ctx, benchmark_id, iterations, output, monitor, visual, save_monitoring):  # Add visual param
    console = ctx.obj['console']
    quiet = ctx.obj['quiet']
    
    if quiet:
        # Quiet mode unchanged
        orch = Orchestrator()
        bench = orch.create_benchmark(benchmark_id, {"iterations": iterations})
        if bench.initialize():
            result = bench.test()
            bench.cleanup()
            if output: _save_result(result, output, console, quiet)
        return
    
    # MODIFIED: Enhanced monitoring setup
    from ..monitoring import create_monitor
    system_monitor = create_monitor(collect_perf=True, collect_memory=True)
    
    # NEW: Add timeseries support if visual mode enabled
    if visual:
        from ..monitoring.timeseries import add_timeseries_support
        system_monitor = add_timeseries_support(system_monitor)
        console.print("[green]✓[/green] Enhanced visual monitoring enabled")
    
    # MODIFIED: Create dashboard with plot support
    from .dashboard import create_enhanced_dashboard  # Use new unified dashboard
    dashboard = create_enhanced_dashboard(console, enable_plots=visual)
    
    # NEW: Set up dashboard for real-time plots
    if visual:
        dashboard.set_streaming_monitor(system_monitor)
    
    try:
        # Setup benchmark (unchanged)
        orch = Orchestrator()
        config = {"iterations": iterations}
        bench = orch.create_benchmark(benchmark_id, config)
        
        if not bench.initialize():
            print(f"❌ Error: Failed to initialize benchmark: {benchmark_id}")
            if hasattr(bench, 'error') and bench.error:
                print(f"❌ Error details: {bench.error}")
            return 1        
        
        if monitor:
            # MODIFIED: Enhanced dashboard run with inference timing
            result = _run_with_enhanced_dashboard(console, bench, benchmark_id, system_monitor, dashboard, visual)
        else:
            # Standard execution
            system_monitor.start_monitoring()
            result = bench.test()
            system_monitor.stop_monitoring()
        
        bench.cleanup()
        
        # Success message (unchanged)
        display_success(console, f"Benchmark '{benchmark_id}' completed successfully!")
        
        if output: _save_result(result, output, console, quiet)
        if save_monitoring: _save_monitoring_data(system_monitor, save_monitoring, console, result)
        
        # NEW: Show performance insights if visual mode
        if visual:
            _show_performance_insights(console, dashboard, result)
        
    except Exception as e:
        display_error(console, f"Benchmark failed: {str(e)}")
        system_monitor.stop_monitoring()
        ctx.exit(1)



@click.command()
@click.argument('config_path', type=click.Path(exists=True))
@click.option('--name', '-n', help='Name for this sweep run')
@click.option('--output-dir', '-o', type=click.Path(), help='Output directory for results')
@click.option('--monitor/--no-monitor', default=True, help='Show live dashboard')
@click.option('--save-monitoring', type=click.Path(), help='Save monitoring data to file')
@click.pass_context
def sweep(ctx, config_path, name, output_dir, monitor, save_monitoring):
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
    
    system_monitor = create_monitor(collect_perf=True)
    
    dashboard = DashboardLayout(console)
    
    try:
        # Load and validate config
        config = SweepConfig.load(config_path)
        combinations = config.generate_combinations()
        
        console.print(f"[info]Generated [metric]{len(combinations)}[/metric] benchmark combinations[/info]")
        
        system_monitor.start_monitoring()
        time.sleep(0.1)  # Brief delay to get initial readings
        stats = system_monitor.get_current_metrics()
        
        console.print(f"[info]Running on: [benchmark]{stats.get('pi_model', 'Unknown')}[/benchmark][/info]")
        console.print()
        
        # Setup sweep
        orch = Orchestrator()
        sweep_runner = Sweep(orch)
        
        if monitor:
            results = _run_sweep_with_inline_dashboard(console, sweep_runner, config_path, combinations, system_monitor, dashboard, name or "sweep")
        else:
            results = sweep_runner.run(config_path)
            system_monitor.stop_monitoring()
        
        # Display final results table (after dashboard)
        display_success(console, f"Sweep completed! {len(results)} benchmarks executed.")
        
        # Save results if requested
        if output_dir:
            _save_sweep_results(results, output_dir, name, console, quiet)
        if save_monitoring:
            _save_monitoring_data(system_monitor, save_monitoring, console, results)
            
    except Exception as e:
        display_error(console, f"Sweep failed: {str(e)}")
        system_monitor.stop_monitoring()  # Make sure to stop monitoring
        ctx.exit(1)


def _run_with_enhanced_dashboard(console, bench, benchmark_id, system_monitor, dashboard, visual_mode):
    """Run benchmark with enhanced dashboard including optional real-time plots."""
    from rich.live import Live
    
    # Dashboard stages
    stages = ["initializing", "loading", "computing", "finalizing", "complete"]
    
    # Start monitoring
    system_monitor.start_monitoring()
    
    # Initial dashboard setup
    dashboard.update_header(f"Running: {benchmark_id}")
    dashboard.update_system_tiles(system_monitor.get_current_metrics())
    dashboard.update_progress(stages[0], 0, [], stages[1:])
    dashboard.update_results()
    dashboard.update_footer("Starting benchmark...")
    
    # Use Live with appropriate refresh rate
    refresh_rate = 1 if visual_mode else 2  # Slower refresh for plots
    with Live(dashboard.render(), refresh_per_second=refresh_rate, console=console, transient=True) as live:
        
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
            dashboard.update_system_tiles(system_monitor.get_current_metrics())
            dashboard.update_progress(current_stage, progress_percent, past_stages, future_stages)
            dashboard.update_footer(f"Progress: {progress_percent}% - {current_stage}")
            
            live.update(dashboard.render())
        
        # Run actual benchmark with inference timing tracking
        if visual_mode and hasattr(dashboard, 'add_inference_timing'):
            result = _run_benchmark_with_timing_tracking(bench, dashboard)
        else:
            result = bench.test()
        
        # Final update
        dashboard.update_progress("complete", 100, stages[:-1], [])
        dashboard.update_results(result)
        dashboard.update_footer("Benchmark completed!")
        live.update(dashboard.render())
        
        time.sleep(1)  # Show final state briefly
    
    system_monitor.stop_monitoring()
    return result


# NEW: Benchmark execution with inference timing tracking
def _run_benchmark_with_timing_tracking(bench, dashboard):
    """Run benchmark and feed inference timings to dashboard for real-time event detection."""
    
    # Check if benchmark supports timing callbacks
    if hasattr(bench, 'test_with_timing_callback'):
        # Enhanced benchmark that can report individual inference times
        return bench.test_with_timing_callback(dashboard.add_inference_timing)
    else:
        # Standard benchmark - simulate timing from iterations
        import time
        start_time = time.time()
        
        # Run standard test
        result = bench.test()
        
        # Simulate inference timing from total time and iterations
        if 'iterations' in bench.config and 'mean_inference_ms' in result:
            mean_ms = result['mean_inference_ms']
            iterations = bench.config['iterations']
            
            # Add a few timing samples for event detection
            for i in range(min(10, iterations // 10)):  # Sample 10 times during execution
                simulated_ms = mean_ms + ((-1) ** i) * (mean_ms * 0.2)  # Add some variance
                dashboard.add_inference_timing(simulated_ms)
        
        return result


# NEW: Performance insights display
def _show_performance_insights(console, dashboard, benchmark_result):
    """Show performance insights from enhanced monitoring."""
    try:
        if not hasattr(dashboard, 'timeseries_extension') or not dashboard.timeseries_extension:
            return
        
        # Get events from dashboard
        events = dashboard.timeseries_extension.get_events_timeline(window_seconds=300)
        
        if not events:
            console.print("[dim]No performance events detected[/dim]")
            return
        
        console.print("\n[bold cyan]Performance Insights:[/bold cyan]")
        
        # Analyze events
        slow_inferences = [e for e in events if e.get('type') == 'slow_inference']
        memory_spikes = [e for e in events if e.get('type') == 'memory_spike']
        
        if slow_inferences:
            console.print(f"[yellow]⚠️  {len(slow_inferences)} slow inference events detected[/yellow]")
            worst = max(slow_inferences, key=lambda e: e.get('slowdown_factor', 1))
            factor = worst.get('slowdown_factor', 1)
            console.print(f"   Worst: {factor:.1f}x slower at {worst.get('timestamp', 0):.1f}s")
        
        if memory_spikes:
            console.print(f"[blue]📈 {len(memory_spikes)} memory events detected[/blue]")
            largest = max(memory_spikes, key=lambda e: abs(e.get('delta_mb', 0)))
            delta = largest.get('delta_mb', 0)
            console.print(f"   Largest: {abs(delta):.1f}MB spike at {largest.get('timestamp', 0):.1f}s")
        
        # Performance variance analysis
        mean_ms = benchmark_result.get('mean_inference_ms', 0)
        max_ms = benchmark_result.get('max_inference_ms', 0)
        min_ms = benchmark_result.get('min_inference_ms', 0)
        
        if max_ms > 0 and min_ms > 0:
            variance = max_ms / min_ms
            if variance > 3.0:
                console.print(f"[yellow]📊 High variance: {variance:.1f}x difference (min: {min_ms:.1f}ms, max: {max_ms:.1f}ms)[/yellow]")
        
        console.print()
        
    except Exception as e:
        console.print(f"[dim red]Could not analyze insights: {e}[/dim red]")

def _save_monitoring_data(monitor, output_path, console, benchmark_result=None):
    """Save monitoring data with benchmark results."""
    try:
        import json
        
        # Export all collected monitoring data
        export_data = monitor.export_data()
        
        # Add benchmark result to the export
        if benchmark_result:
            export_data['benchmark_result'] = benchmark_result
        
        # Add summary statistics - now duration will be calculated correctly
        metrics = monitor.get_all_metric_types()
        
        # Duration is now calculated in export_data, but let's add more summary info
        duration = export_data.get('collection_duration', 0.0)
        
        export_data['summary'] = {
            'total_metrics_collected': len(metrics),
            'metric_types': metrics,
            'collection_duration': duration,
            'start_time': export_data.get('start_time'),
            'end_time': export_data.get('end_time'),
            'total_samples': sum(len(samples) for samples in export_data['metrics'].values())
        }
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        console.print(f"[green]✓[/green] Monitoring data saved to {output_path}")
        console.print(f"[info]Collected {len(metrics)} metric types over {duration:.1f}s[/info]")
        
        # Show some additional stats
        total_samples = export_data['summary']['total_samples']
        if duration > 0:
            sample_rate = total_samples / duration
            console.print(f"[info]Total samples: {total_samples} ({sample_rate:.1f} samples/sec)[/info]")
        
    except Exception as e:
        console.print(f"[red]Failed to save monitoring data: {e}[/red]")
        # Add debug info
        import traceback
        console.print(f"[dim]Debug: {traceback.format_exc()}[/dim]")
        
def _run_sweep_with_inline_dashboard(console, sweep_runner, config_path, combinations, system_monitor, dashboard, sweep_name):
    """Run sweep with inline dashboard that refreshes in place"""
    from rich.live import Live
    
    dashboard.update_header(f"Sweep: {sweep_name}")
    dashboard.update_system_tiles(system_monitor.get_current_metrics())
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

            dashboard.update_system_tiles(system_monitor.get_current_metrics())            
            dashboard.update_progress("executing", progress_percent, ["starting"], ["finishing"])
            dashboard.update_footer(f"Running benchmark {i+1}/{total_benchmarks}...")
            
            live.update(dashboard.render())
            time.sleep(0.3)  # Brief pause
        
        results = sweep_runner.run(config_path)
        
        dashboard.update_progress("complete", 100, ["starting", "executing"], [])
        dashboard.update_footer(f"Completed {len(results)} benchmarks!")
        live.update(dashboard.render())
        
        time.sleep(1)
    
    system_monitor.stop_monitoring()    
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