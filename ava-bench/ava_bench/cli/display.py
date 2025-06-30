def display_error(console, message):
    """Display error message"""
    console.print(f"[red bold]ERROR: {message}[/red bold]")


def display_warning(console, message):
    """Display warning message"""
    console.print(f"[yellow bold]WARNING: {message}[/yellow bold]")


def display_success(console, message):
    """Display success message"""
    console.print(f"[green bold]SUCCESS: {message}[/green bold]")