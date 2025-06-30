# ava_bench/cli/commands.py

import time
import click
import shlex

from ..core.orchestrator import Orchestrator
from ..runner import print_results
from .display import display_error, display_success


@click.command()
@click.argument('command', nargs=-1, required=True)
@click.option('--timeout', '-t', type=int, help='Timeout in seconds')
@click.option('--output', '-o', type=click.Path(), help='Output file for results')
@click.option('--monitor/--no-monitor', default=True, help='Enable system monitoring')
@click.option('--sampling-rate', default=1.0, help='Monitoring sampling rate in Hz')
@click.option('--save-monitoring', type=click.Path(), help='Save monitoring data to file')
@click.pass_context
def run(ctx, command, timeout, output, monitor, sampling_rate, save_monitoring):
    """
    Run an executable command with optional monitoring.
    
    COMMAND can be multiple arguments, e.g.:
    ava-bench run echo "hello world"
    ava-bench run python -c "print('hello')"
    ava-bench run ls -la
    """
    console = ctx.obj['console']
    quiet = ctx.obj['quiet']
    
    # Convert command tuple to list
    command_list = list(command)
    
    if not quiet:
        console.print(f"[info]Running command: [benchmark]{' '.join(command_list)}[/benchmark][/info]")
        if timeout:
            console.print(f"[info]Timeout: [metric]{timeout}s[/metric][/info]")
        if monitor:
            console.print(f"[info]Monitoring enabled at [metric]{sampling_rate}Hz[/metric][/info]")
        console.print()
    
    try:
        # Setup orchestrator
        orch = Orchestrator()
        
        if monitor:
            orch.setup_monitoring(sampling_rate_hz=sampling_rate)
        
        # Run the executable
        result = orch.run_executable(
            command=command_list,
            timeout=timeout,
            output_file=output,
            enable_monitoring=monitor
        )
        
        # Display results
        if not quiet:
            print_results(result)
            display_success(console, f"Command completed successfully!")
        else:
            # In quiet mode, just show if it succeeded or failed
            if result['metadata']['success']:
                console.print("PASS")
            else:
                console.print("FAIL")
                ctx.exit(1)
        
        # Save monitoring data if requested
        if save_monitoring and result.get('monitoring', {}).get('full_data'):
            _save_monitoring_data(result['monitoring']['full_data'], save_monitoring, console)
        
    except Exception as e:
        display_error(console, f"Command failed: {str(e)}")
        ctx.exit(1)


def _save_monitoring_data(monitoring_data, filepath, console):
    """Save monitoring data to file."""
    import json
    from pathlib import Path
    
    try:
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(monitoring_data, f, indent=2, default=str)
        
        console.print(f"[success]Monitoring data saved to: {filepath}[/success]")
    except Exception as e:
        console.print(f"[error]Failed to save monitoring data: {e}[/error]")


@click.command()
@click.pass_context
def list_commands(ctx):
    """List some common executable commands that can be run."""
    console = ctx.obj['console']
    
    orch = Orchestrator()
    commands = orch.list_available_commands()
    
    console.print("[info]Common executable commands you can run:[/info]")
    for cmd in commands:
        console.print(f"  • {cmd}")
    
    console.print("\n[info]You can run any executable with arguments:[/info]")
    console.print("  ava-bench run python -c \"print('hello')\"")
    console.print("  ava-bench run echo \"test message\"")
    console.print("  ava-bench run ls -la")


@click.command()
@click.pass_context
def system_info(ctx):
    """Display system information."""
    console = ctx.obj['console']
    
    orch = Orchestrator()
    info = orch.get_system_info()
    
    console.print("[info]System Information:[/info]")
    for key, value in info.items():
        console.print(f"  {key}: {value}")
    
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