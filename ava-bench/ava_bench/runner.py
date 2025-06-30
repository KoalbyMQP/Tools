"""
AVA-Bench Executable Runner - Single file execution system
Run any executable with monitoring. Keep it simple.
"""

import subprocess
import json
import time
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


def validate_executable(command: List[str]) -> None:
    """Check if command is valid and executable exists."""
    assert command, "Command cannot be empty"
    
    executable = command[0]
    
    # Check if it's an absolute/relative path
    if '/' in executable or '\\' in executable:
        exe_path = Path(executable)
        assert exe_path.exists(), f"Executable not found: {executable}"
        assert exe_path.is_file(), f"Path is not a file: {executable}"
        # Note: We can't easily check execute permissions cross-platform, let subprocess handle it
    else:
        # Check if it's in PATH
        assert shutil.which(executable), f"Executable not found in PATH: {executable}"


def execute_with_monitoring(command: List[str], timeout: Optional[int] = None, 
                          monitor=None) -> Dict[str, Any]:
    """Execute command with optional monitoring."""
    result = {
        'command': command,
        'start_time': time.time(),
        'success': False,
        'exit_code': None,
        'stdout': '',
        'stderr': '',
        'duration': 0.0,
        'monitoring_data': None
    }
    
    # Start monitoring if provided
    if monitor:
        monitor.start_monitoring()
        time.sleep(0.1)  # Brief delay to stabilize monitoring
    
    start_time = time.perf_counter()
    
    try:
        # Execute the command
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False  # Don't raise on non-zero exit
        )
        
        result.update({
            'success': process.returncode == 0,
            'exit_code': process.returncode,
            'stdout': process.stdout,
            'stderr': process.stderr,
            'duration': time.perf_counter() - start_time
        })
        
    except subprocess.TimeoutExpired:
        result.update({
            'success': False,
            'exit_code': -1,
            'stderr': f"Command timed out after {timeout} seconds",
            'duration': time.perf_counter() - start_time
        })
        
    except FileNotFoundError:
        result.update({
            'success': False,
            'exit_code': -1,
            'stderr': f"Executable not found: {command[0]}",
            'duration': time.perf_counter() - start_time
        })
    
    # Stop monitoring and collect data
    if monitor:
        time.sleep(0.1)  # Brief delay to capture final state
        monitor.stop_monitoring()
        result['monitoring_data'] = monitor.export_data()
    
    return result


def parse_executable_results(stdout: str, stderr: str, exit_code: int) -> Dict[str, Any]:
    """Parse results from executable output."""
    parsed_result = {
        'executable_output': {
            'exit_code': exit_code,
            'success': exit_code == 0
        }
    }
    
    # Try to parse JSON from stdout
    if stdout.strip():
        try:
            # Look for JSON object in stdout (might have other text too)
            lines = stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    json_data = json.loads(line)
                    parsed_result['executable_output'].update(json_data)
                    break
            else:
                # No JSON found, store raw output
                parsed_result['executable_output']['raw_stdout'] = stdout
                
        except json.JSONDecodeError:
            # Not valid JSON, store as raw output
            parsed_result['executable_output']['raw_stdout'] = stdout
    
    # Include stderr if present (usually indicates issues)
    if stderr.strip():
        parsed_result['executable_output']['stderr'] = stderr
    
    return parsed_result


def combine_results(execution_result: Dict[str, Any], 
                   parsed_output: Dict[str, Any]) -> Dict[str, Any]:
    """Combine execution metadata with parsed executable results."""
    
    # Calculate monitoring summary if available
    monitoring_summary = {}
    if execution_result.get('monitoring_data'):
        monitoring_data = execution_result['monitoring_data']
        
        # Extract key metrics from monitoring data
        if 'metrics' in monitoring_data:
            # Get final values for key metrics
            for metric_name, samples in monitoring_data['metrics'].items():
                if samples and isinstance(samples, list):
                    latest_sample = samples[-1]
                    if isinstance(latest_sample, dict) and 'value' in latest_sample:
                        monitoring_summary[metric_name] = latest_sample['value']
    
    combined = {
        'metadata': {
            'command': execution_result['command'],
            'start_time': execution_result['start_time'],
            'duration_seconds': execution_result['duration'],
            'success': execution_result['success'] and parsed_output['executable_output']['success'],
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        },
        'results': parsed_output['executable_output'],
        'monitoring': {
            'summary': monitoring_summary,
            'full_data': execution_result.get('monitoring_data')
        }
    }
    
    # Include execution errors if any
    if not execution_result['success']:
        combined['metadata']['execution_error'] = execution_result.get('stderr', 'Unknown error')
    
    return combined


def run_executable(command: List[str], *, monitor=None, timeout: Optional[int] = None, 
                  output_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Run any executable with monitoring. Main entry point.
    
    Args:
        command: List of command and arguments ['./benchmark', '--arg1', 'val1']
        monitor: Optional monitoring instance
        timeout: Optional timeout in seconds
        output_file: Optional file to save results
        
    Returns:
        Combined results dictionary
    """
    
    # Validate inputs
    validate_executable(command)
    
    if timeout is not None:
        assert timeout > 0, f"Timeout must be positive, got: {timeout}"
    
    # Execute with monitoring
    execution_result = execute_with_monitoring(command, timeout, monitor)
    
    # Parse executable output
    parsed_output = parse_executable_results(
        execution_result['stdout'],
        execution_result['stderr'], 
        execution_result['exit_code']
    )
    
    # Combine everything
    final_result = combine_results(execution_result, parsed_output)
    
    # Save to file if requested
    if output_file:
        save_results(final_result, output_file)
    
    return final_result


def save_results(results: Dict[str, Any], filepath: str) -> None:
    """Save results to JSON file."""
    output_path = Path(filepath)
    
    # Create parent directories if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)  # default=str handles non-serializable types
    except Exception as e:
        raise RuntimeError(f"Failed to save results to {filepath}: {e}")


def print_results(results: Dict[str, Any]) -> None:
    """Print results in a human-readable format."""
    metadata = results['metadata']
    executable_results = results['results']
    monitoring = results['monitoring']['summary']
    
    print(f"\n{'='*60}")
    print(f"AVA-Bench Results")
    print(f"{'='*60}")
    
    print(f"Command: {' '.join(metadata['command'])}")
    print(f"Duration: {metadata['duration_seconds']:.3f}s")
    print(f"Success: {'PASS' if metadata['success'] else 'FAIL'}")
    
    if not metadata['success']:
        print(f"Error: {metadata.get('execution_error', 'Unknown error')}")
    
    # Print executable results
    print(f"\nExecutable Results:")
    for key, value in executable_results.items():
        if key not in ['exit_code', 'success', 'stderr', 'raw_stdout']:
            print(f"  {key}: {value}")
    
    # Print key monitoring metrics
    if monitoring:
        print(f"\nSystem Monitoring:")
        for metric, value in monitoring.items():
            if 'cpu' in metric.lower():
                print(f"  {metric}: {value}")
            elif 'memory' in metric.lower():
                print(f"  {metric}: {value}")
        
    print(f"{'='*60}\n")


# Example usage and testing
if __name__ == "__main__":
    # Simple test - run echo command
    test_command = ['echo', '{"duration": 1.23, "throughput": 1000}']
    
    print("Testing executable runner...")
    result = run_executable(test_command)
    print_results(result)