# ava_bench/cli/main.py

import click
from rich.console import Console
from .cli.commands import run

@click.group()
@click.option('--quiet', '-q', is_flag=True, help='Suppress non-essential output')
@click.pass_context
def cli(ctx, quiet):
    """
    AVA-Bench: Benchmarking suite for Raspberry Pi devices
    
    Run and monitor executables with detailed performance metrics.
    """
    # Ensure the context object exists
    ctx.ensure_object(dict)
    
    # Store shared configuration
    ctx.obj['console'] = Console()
    ctx.obj['quiet'] = quiet


# Add commands to the CLI group
cli.add_command(run)


if __name__ == '__main__':
    cli()