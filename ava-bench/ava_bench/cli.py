# ava_bench/cli/commands.py

import click
import time
from .runner import run_executable
from rich.live import Live
from rich.text import Text


@click.command()
@click.argument('command', nargs=-1, required=True)
@click.option('--timeout', '-t', type=int, help='Timeout in seconds')
@click.option('--output', '-o', type=click.Path(), help='Output file for results')
@click.option('--monitor/--no-monitor', default=True, help='Enable system monitoring')
@click.option('--save-monitoring', type=click.Path(), help='Save monitoring data to file')
@click.pass_context
def run(ctx, command, timeout, output, monitor, save_monitoring):
    """
    Run an executable command with optional monitoring.
    
    Examples:
        ava-bench run echo "hello world"
        ava-bench run python -c "print('hello')"
        ava-bench run ls -la
    """
    console = ctx.obj['console']
    quiet = ctx.obj['quiet']
    
    command_list = list(command)
    command_str = ' '.join(command_list)
    
    # Handle quiet mode simply
    if quiet:
        try:
            monitor_instance = None
            if monitor:
                from .monitoring import create_monitor
                monitor_instance = create_monitor()
            
            result = run_executable(
                command=command_list,
                monitor=monitor_instance,
                timeout=timeout,
                output_file=output
            )
            
            if result['metadata']['success']:
                console.print("PASS")
            else:
                console.print("FAIL")
                ctx.exit(1)
                
        except Exception as e:
            console.print("FAIL")
            ctx.exit(1)
        return
    
    # Rich interactive mode
    try:
        # Phase 1: Fast overlapping setup
        with console.status("[bold cyan]⠋ Preparing execution environment...") as status:
            monitor_instance = None
            
            if monitor:
                status.update("[bold cyan]⠙ Starting system monitoring...")
                from .monitoring import create_monitor
                monitor_instance = create_monitor()
            
            status.update("[bold cyan]⠹ Environment ready")
        
        # Clear completion of setup
        console.print("[bold cyan]✓[/bold cyan] Environment ready")
        
        # Phase 2: Static execution line + live metrics below
        console.print(f"[bold green]Executing:[/bold green] [white]{command_str}[/white]")
        
        start_time = time.time()
        result = _run_with_live_metrics(
            command_list, monitor_instance, timeout, output, console
        )
        total_time = time.time() - start_time
        
        # Phase 3: Saving phase (new line)
        with console.status("[bold green]⠋ Saving results and exporting data...") as status:
            
            if save_monitoring and result.get('monitoring', {}).get('full_data'):
                _save_monitoring_data(result['monitoring']['full_data'], save_monitoring, console)
            
            # Final status
            if result['metadata']['success']:
                status.update(f"[bold green]✓[/bold green] All complete ([cyan]{total_time:.1f}s total[/cyan])")
            else:
                status.update(f"[bold red]✗[/bold red] Execution failed ([cyan]{total_time:.1f}s total[/cyan])")
                
        # Show final result
        if result['metadata']['success']:
            console.print(f"[green]SUCCESS[/green] Command completed in [cyan]{total_time:.1f}s[/cyan]")
        else:
            console.print(f"[red]FAILED[/red] Command failed")
            ctx.exit(1)
            
    except Exception as e:
        console.print(f"[red]ERROR: {str(e)}[/red]")
        ctx.exit(1)


def _run_with_live_metrics(command_list, monitor_instance, timeout, output_file, console):
    """Run executable with live metrics updates below static execution line."""
    import subprocess
    import threading
    
    # Start monitoring if available
    if monitor_instance:
        monitor_instance.start_monitoring()
    
    # Start the process
    start_time = time.time()
    process = subprocess.Popen(
        command_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Live metrics updates (only the metrics line updates)
    with console.status("") as status:
        def update_metrics():
            duration = 0
            while process.poll() is None:
                duration = time.time() - start_time
                
                # Get live metrics if monitoring is available
                metrics_text = f"PID: {process.pid}"
                
                if monitor_instance:
                    try:
                        current_metrics = monitor_instance.stream_manager.get_all_current_data()
                        cpu_usage = "N/A"
                        memory_mb = "N/A"
                        temp = "N/A"
                        
                        # Extract key metrics
                        for metric_name, sample in current_metrics.items():
                            if 'cpu.usage_percent' in metric_name and sample:
                                cpu_usage = f"{sample.value:.0f}%"
                            elif 'process.memory.rss_mb' in metric_name and sample:
                                memory_mb = f"{sample.value:.0f}MB"
                            elif 'thermal.cpu_temp' in metric_name and sample:
                                temp = f"{sample.value:.0f}°C"
                        
                        metrics_text = f"PID: {process.pid} [dim]│[/] CPU: {cpu_usage} [dim]│[/] Memory: {memory_mb} [dim]│[/] Temp: {temp}"
                    
                    except Exception:
                        pass
                
                # Update only the metrics line with duration
                status.update(f"  [dim]│[/] {metrics_text} [dim]│[/] [yellow]Running for {duration:.1f}s...[/yellow]")
                time.sleep(0.5)
        
        # Start metrics updates in background
        metrics_thread = threading.Thread(target=update_metrics, daemon=True)
        metrics_thread.start()
        
        # Wait for process completion
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            returncode = -1
            stderr = f"Command timed out after {timeout} seconds"
    
    # Show final frozen metrics state
    duration = time.time() - start_time
    final_metrics = f"PID: {process.pid}"
    
    if monitor_instance:
        try:
            # Get final metrics snapshot
            current_metrics = monitor_instance.stream_manager.get_all_current_data()
            cpu_usage = "N/A"
            memory_mb = "N/A" 
            temp = "N/A"
            
            for metric_name, sample in current_metrics.items():
                if 'cpu.usage_percent' in metric_name and sample:
                    cpu_usage = f"{sample.value:.0f}%"
                elif 'process.memory.rss_mb' in metric_name and sample:
                    memory_mb = f"{sample.value:.0f}MB"
                elif 'thermal.cpu_temp' in metric_name and sample:
                    temp = f"{sample.value:.0f}°C"
            
            final_metrics = f"PID: {process.pid} [dim]│[/] CPU: {cpu_usage} [dim]│[/] Memory: {memory_mb} [dim]│[/] Temp: {temp}"
        except Exception:
            pass
        
        # Stop monitoring
        monitor_instance.stop_monitoring()
    
    # Print final frozen state
    if returncode == 0:
        console.print(f"  [dim]│[/] {final_metrics} [dim]│[/] [green]Completed in {duration:.1f}s[/green]")
    else:
        console.print(f"  [dim]│[/] {final_metrics} [dim]│[/] [red]Failed after {duration:.1f}s[/red]")
    
    # Build result
    result = {
        'metadata': {
            'command': command_list,
            'duration_seconds': duration,
            'success': returncode == 0,
            'start_time': start_time
        },
        'results': {
            'exit_code': returncode,
            'success': returncode == 0,
            'stdout': stdout,
            'stderr': stderr
        },
        'monitoring': {
            'summary': {},
            'full_data': monitor_instance.export_data() if monitor_instance else None
        }
    }
    
    # Save output if requested
    if output_file:
        _save_results(result, output_file)
    
    return result


def _save_monitoring_data(monitoring_data, filepath, console):
    """Save monitoring data to JSON file."""
    import json
    from pathlib import Path
    
    try:
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(monitoring_data, f, indent=2, default=str)
        
        # Don't print during status updates, just succeed silently
        
    except Exception as e:
        console.print(f"[red]Failed to save monitoring data: {e}[/red]")


def _save_results(result, filepath):
    """Save results to JSON file."""
    import json
    from pathlib import Path
    
    output_path = Path(filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)