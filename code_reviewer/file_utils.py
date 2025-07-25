"""
File operations and utilities for the code reviewer.
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from .config import Config
from .exceptions import FileError, GitError


def run_command(cmd: List[str]) -> str:
    """Run a shell command and return output, raise GitError on failure.
    
    Args:
        cmd: Command and arguments to execute
        
    Returns:
        Command output as string
        
    Raises:
        GitError: If command fails or is not found
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(f"Command failed: {' '.join(cmd)}\n{e.stderr.strip()}")
    except FileNotFoundError:
        raise GitError(f"Command not found: {cmd[0]}")


def is_supported_file(filepath: str, config: Config) -> bool:
    """Check if file is a supported file we should review.
    
    Args:
        filepath: Path to the file to check
        config: Configuration containing supported extensions
        
    Returns:
        True if file extension is supported, False otherwise
    """
    path = Path(filepath)
    return path.suffix in config.supported_extensions


def count_lines(content: str) -> int:
    """Count non-empty lines in content.
    
    Args:
        content: Text content to count lines in
        
    Returns:
        Number of non-empty lines
    """
    return len([line for line in content.split('\n') if line.strip()])


def read_file_content(filepath: str) -> str:
    """Read file content, raise FileError on failure.
    
    Args:
        filepath: Path to file to read
        
    Returns:
        File content as string
        
    Raises:
        FileError: If file cannot be read
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        raise FileError(f"Error reading {filepath}: {e}")


def get_system_prompt(prompt_file: Optional[str] = None, logger: Optional[logging.Logger] = None) -> str:
    """Get the system prompt for the code review.
    
    Args:
        prompt_file: Custom prompt file path (optional)
        logger: Logger instance for debug output
        
    Returns:
        System prompt content as string
        
    Raises:
        FileError: If no prompt file can be found or read
    """
    if logger is None:
        logger = logging.getLogger('codereviewer')
        
    if prompt_file:
        prompt_file_path = Path(prompt_file).expanduser()
        if not prompt_file_path.exists():
            raise FileError(f"Prompt file {prompt_file_path} does not exist")
        logger.info(f"Using custom prompt file: {prompt_file_path}")
        try:
            with open(prompt_file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (PermissionError, UnicodeDecodeError) as e:
            raise FileError(f"Error reading prompt file {prompt_file_path}: {e}")

    default_prompt_locations = [
        Path("~/.code-review-prompt.md").expanduser(), 
        Path(__file__).parent.parent / "system_prompt.md"
    ]
    
    for prompt_path in default_prompt_locations:
        if prompt_path.exists():
            logger.info(f"Using default prompt file: {prompt_path}")
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return f.read()
            except (PermissionError, UnicodeDecodeError) as e:
                logger.debug(f"Failed to read {prompt_path}: {e}")
                continue  # Try next location

    raise FileError(f"No prompt file found in {default_prompt_locations}")