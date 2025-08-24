# ava_bench/__main__.py

<<<<<<< HEAD
from .cli import cli

def main():
    """Main entry point for the CLI"""
    cli()

if __name__ == "__main__":
    main()
=======
import click
from rich.console import Console
from .cli import run

@click.group()
@click.option('--quiet', '-q', is_flag=True, help='Suppress non-essential output')
@click.pass_context
def cli(ctx, quiet):
    """TODO: Add good text here."""
    ctx.ensure_object(dict)
    ctx.obj['console'] = Console()
    ctx.obj['quiet'] = quiet

cli.add_command(run)

if __name__ == '__main__':
    cli()
>>>>>>> main
