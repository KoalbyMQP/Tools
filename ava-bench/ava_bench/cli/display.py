from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout

def display_error(console, message):
    """Display error message"""
    console.print(f"[red bold]❌ Error: {message}[/red bold]")


def display_warning(console, message):
    """Display warning message"""
    console.print(f"[yellow bold]⚠️  Warning: {message}[/yellow bold]")


def display_success(console, message):
    """Display success message"""
    console.print(f"[green bold]✅ {message}[/green bold]")