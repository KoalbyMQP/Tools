# ava_bench/cli/commands.py

import click
from .runner import run_executable, print_results

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
    
    if not quiet:
        display_info(console, f"Running: {' '.join(command_list)}")
        if timeout:
            display_info(console, f"Timeout: {timeout}s")
        if monitor:
            display_info(console, "System monitoring enabled")
    
    try:
        # Setup basic monitoring if requested
        monitor_instance = None
        if monitor:
            from .monitoring import create_monitor
            monitor_instance = create_monitor()
        
        # Run the executable
        result = run_executable(
            command=command_list,
            monitor=monitor_instance,
            timeout=timeout,
            output_file=output
        )
        
        # Display results
        if not quiet:
            print_results(result)
            display_success(console, "Command completed")
        else:
            # In quiet mode, just show pass/fail
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
    """Save monitoring data to JSON file."""
    import json
    from pathlib import Path
    
    try:
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(monitoring_data, f, indent=2, default=str)
        
        console.print(f"[green]Monitoring data saved to: {filepath}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to save monitoring data: {e}[/red]")

def display_error(console, message):
    console.print(f"[red]ERROR: {message}[/red]")

def display_success(console, message):
    console.print(f"[green]✓ {message}[/green]")

def display_info(console, message):
    console.print(f"[blue]ℹ {message}[/blue]")