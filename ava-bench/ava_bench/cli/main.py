import click
from rich.console import Console
from rich.theme import Theme

# Shared Rich console with custom theme
console_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green bold",
    "benchmark": "blue bold",
    "metric": "magenta",
    "progress": "bright_blue"
})

console = Console(theme=console_theme)

@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="ava-bench")
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--quiet', '-q', is_flag=True, help='Minimal output only')
@click.pass_context
def cli(ctx, verbose, quiet):
    """🔥 AVA-Bench: ML Benchmarking Suite for Raspberry Pi"""
    
    # Ensure context object exists
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet
    ctx.obj['console'] = console
    
    # Show help if no command provided
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Import and register commands
from .commands import run, sweep, frameworks

cli.add_command(run)
cli.add_command(sweep)
cli.add_command(frameworks)