import typer
from pathlib import Path
from typing import List
from rolint.config import load_config, save_config
from rolint.main import run_linter

##Main entry point for command line with rolint
app = typer.Typer(help="Rolint - Linter for robotics code (C, C++, Python)")

@app.command()
def check(
    paths: List[Path] = typer.Argument(..., help="Path(s) to folder or file to lint"),
    lang: str = typer.Option(None, "--lang", "-l", help="Optional: Force language (c | cpp | python)"),
    output: str = typer.Option("text", "--output", "-o", help="Output format: text | json"),
    output_path: Path = typer.Option(None, "--output-path", "-p", help="Optional: Path to write JSON output"),
):
    """
    Run safety checks on code.

    Examples: \n
      rolint check [OPTIONS] PATH [PATH ...] checks file[s] at specified path(s) \n
      rolint check file1.py file2.py file3.py \n
      rolint check src/ \n
      rolint check . \n
    """

    config = load_config()
    output_path_str = output_path or config.get("output_path") or "rolint_results.json"
    true_output_path = Path(output_path_str)
    
    # Process each path
    exit_code = 0
    for path in paths:
        try:
            run_linter(path, lang=lang, output_format=output, output_path=true_output_path)
        except Exception as e:
            typer.echo(f"Error processing {path}: {e}", err=True)
            exit_code = 1
    
    # Exit with error code if any files had issues
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command()
def set_config(
    output_path: str = typer.Option(..., "--output-path", "-p", help="Set default output path for JSON reports")
):
    """
    Set persistent configuration options for rolint. \n

    """
    config = load_config()
    config["output_path"] = output_path
    save_config(config)
    typer.echo(f"✅ Output path set to: {output_path}")

@app.command()
def show_config():
    """
    Show current configuartion settings.
    """
    from rolint.config import load_config
    config = load_config()
    typer.echo("Current configuration:")
    for key, value in config.items():
        typer.echo(f"  {key}: {value}")