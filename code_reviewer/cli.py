"""
Command line interface and argument parsing for the code reviewer.
"""

import argparse
from pathlib import Path

from .config import Config
from .time_parser import parse_time_duration


def validate_max_lines(value: str) -> int:
    """Validate max-lines argument.
    
    Args:
        value: String value from command line
        
    Returns:
        Validated integer value
        
    Raises:
        argparse.ArgumentTypeError: If value is invalid
    """
    try:
        int_value = int(value)
        if int_value <= 0:
            raise argparse.ArgumentTypeError(f"max-lines must be positive, got {int_value}")
        if int_value > 10000:
            raise argparse.ArgumentTypeError(f"max-lines too large (max 10000), got {int_value}")
        return int_value
    except ValueError:
        raise argparse.ArgumentTypeError(f"max-lines must be an integer, got '{value}'")


def validate_model_name(value: str) -> str:
    """Validate model name argument.
    
    Args:
        value: Model name from command line
        
    Returns:
        Validated model name
        
    Raises:
        argparse.ArgumentTypeError: If model name format is invalid
    """
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("model name cannot be empty")
    
    # Basic validation - should contain provider/model format
    if '/' not in value:
        raise argparse.ArgumentTypeError(f"model should be in format 'provider/model', got '{value}'")
    
    return value.strip()


def validate_prompt_file(value: str) -> str:
    """Validate prompt file argument.
    
    Args:
        value: Prompt file path from command line
        
    Returns:
        Validated file path
        
    Raises:
        argparse.ArgumentTypeError: If file doesn't exist or isn't readable
    """
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("prompt file path cannot be empty")
    
    file_path = Path(value.strip()).expanduser()
    if not file_path.exists():
        raise argparse.ArgumentTypeError(f"prompt file does not exist: {file_path}")
    
    if not file_path.is_file():
        raise argparse.ArgumentTypeError(f"prompt file path is not a file: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Try to read first few bytes to check if it's readable
            f.read(100)
    except (PermissionError, UnicodeDecodeError) as e:
        raise argparse.ArgumentTypeError(f"cannot read prompt file {file_path}: {e}")
    
    return str(file_path)


def validate_since_time(value: str) -> str:
    """Validate since time argument.
    
    Args:
        value: Time specification from command line
        
    Returns:
        Validated time string
        
    Raises:
        argparse.ArgumentTypeError: If time format is invalid
    """
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("since time cannot be empty")
    
    try:
        # Test parsing to validate format
        parse_time_duration(value.strip())
        return value.strip()
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def create_parser(config: Config) -> argparse.ArgumentParser:
    """Create and configure the argument parser.
    
    Args:
        config: Configuration instance for defaults
        
    Returns:
        Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description="Friendly LLM code review tool",
        epilog="Examples:\n  cr                           # Review changed files\n  cr app/Models/User.php       # Review specific file",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'file',
        nargs='?',
        help='Specific file to review (if not provided, reviews git changes)'
    )
    parser.add_argument(
        '--since',
        type=validate_since_time,
        default='today',
        metavar='TIME',
        help="Review changes since a specific time (default: 'today'). Formats: 'today', '1h', '30m', '2d'"
    )
    parser.add_argument(
        '--since-commit',
        type=str,
        default=None,
        metavar='COMMIT',
        help='Review changes since a specific commit'
    )
    parser.add_argument(
        '--max-lines',
        type=validate_max_lines,
        default=config.max_single_file_lines,
        metavar='N',
        help=f'Maximum lines for single file review (default: {config.max_single_file_lines})'
    )
    parser.add_argument(
        '--model',
        type=validate_model_name,
        default=config.default_model,
        metavar='PROVIDER/MODEL',
        help=f'Model to use for code review (default: {config.default_model})'
    )
    parser.add_argument(
        '--prompt-file',
        type=validate_prompt_file,
        default=None,
        metavar='FILE',
        help='Specific prompt file to use for this run'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode with verbose logging'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Automatically answer yes to prompts (useful for CI/automation)'
    )
    return parser