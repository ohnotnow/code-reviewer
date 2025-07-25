"""
Output formatting and display functionality for the code reviewer.
"""

import logging
import shutil
import subprocess
from typing import Optional

from .config import Config


def has_glow() -> bool:
    """Check if glow markdown renderer is available.
    
    Returns:
        True if glow command is available, False otherwise
    """
    return shutil.which('glow') is not None


def display_review(review: str, config: Config, logger: Optional[logging.Logger] = None) -> None:
    """Display the review using glow if available, otherwise plain text.
    
    Args:
        review: Review content to display
        config: Configuration containing glow style settings
        logger: Logger for warnings and debug output
    """
    if logger is None:
        logger = logging.getLogger('codereviewer')
        
    print("\n" + "="*60)
    
    # Check if review content exists
    if not review or not review.strip():
        logger.warning("No review content received from LLM")
        print("="*60)
        return
    
    # Try to use glow for better formatting
    if has_glow():
        try:
            result = subprocess.run(
                ['glow', '-s', config.glow_style], 
                input=review.encode('utf-8'),
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout:
                print(result.stdout.decode('utf-8'))
            else:
                # Fallback to plain text if glow fails
                print(review)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            # Fallback to plain text if glow has issues
            print(review)
    else:
        print(review)
    
    print("="*60)