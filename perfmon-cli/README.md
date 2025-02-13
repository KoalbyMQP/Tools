# PerfMon CLI

PerfMon CLI is a command-line tool for profiling the system resource usage of any command. It monitors key performance metrics such as CPU usage, memory consumption, I/O activity, and network usage, providing real-time feedback as well as detailed reports after execution.

## Overview

PerfMon CLI allows you to execute any command and gather performance metrics during its runtime using the command line.

## Requirements

- Python 3.x
- [psutil](https://pypi.org/project/psutil/)
- [rich](https://pypi.org/project/rich/)
- [plotext](https://pypi.org/project/plotext/)
- [PyYAML](https://pypi.org/project/PyYAML/)
- [pandas](https://pypi.org/project/pandas/)

## Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   ```

2. Navigate to the project directory:

   ```bash
   cd perfmon-cli
   ```

3. (Optional) Create a virtual environment and install the dependencies:

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## Usage

Run the PerfMon CLI by specifying the command to monitor. For example:

```bash
python main.py python your_script.py
```

### Command-line Arguments

- `--config`: (Optional) Path to a YAML configuration file. Overrides default settings.
- `--interval`: (Optional) Sampling interval in seconds. Overrides the sampling interval specified in the configuration file.

## Configuration

The default configuration is provided in `config.yaml` and includes:

- `sampling_interval`: Sampling interval (in seconds) for metrics collection.
- `monitor_network`: Boolean flag to enable network monitoring.
- `export_formats`: List of output formats (e.g., `json`, `csv`).
- `show_live_metrics`: Boolean flag to display live metrics on the terminal.
- `create_plots`: Boolean flag to generate terminal-based plots.

You can create your own configuration file to override these defaults.

## Output

After the monitored command completes:

- **JSON Report**: `perfmon_results.json` contains a summary and detailed metrics.
- **CSV Report**: `perfmon_results.csv` contains detailed metrics logs.
- **Plots**: Terminal-based plots of CPU and memory usage are displayed (and can be saved if configured).
