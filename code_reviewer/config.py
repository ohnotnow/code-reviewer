"""
Configuration management for the code reviewer.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Set


@dataclass
class Config:
    """Configuration settings for the code reviewer.
    
    Attributes:
        max_single_file_lines: Maximum lines allowed for single file review
        max_total_diff_lines: Maximum lines allowed for diff review
        supported_extensions: File extensions that can be reviewed
        default_model: Default LLM model to use
        max_tokens: Maximum tokens for LLM response
        temperature: LLM temperature setting (0.0-1.0)
        glow_style: Style theme for glow markdown rendering
    """
    max_single_file_lines: int = 500
    max_total_diff_lines: int = 1000
    supported_extensions: Set[str] = frozenset({'.php', '.py', '.js'})
    default_model: str = "openai/o4-mini"
    max_tokens: int = 100000
    temperature: float = 0.3
    glow_style: str = "dracula"
    # Token estimation constants
    token_estimate_chars_per_token: int = 4  # Rough estimate: 4 chars per token
    max_estimated_tokens: int = 100000  # Conservative limit for most models
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load config from environment variables if needed.
        
        Environment variables:
            CODE_REVIEW_MODEL: Default LLM model (e.g., "openai/gpt-4")
            CODE_REVIEW_MAX_TOKENS: Maximum tokens for LLM response
            CODE_REVIEW_TEMPERATURE: LLM temperature (0.0-1.0)
            CODE_REVIEW_MAX_SINGLE_FILE_LINES: Max lines for single file review
            CODE_REVIEW_MAX_TOTAL_DIFF_LINES: Max lines for diff review
            CODE_REVIEW_GLOW_STYLE: Glow markdown style theme
        
        Returns:
            Config instance with settings from environment or defaults
        """
        def get_int_env(key: str, default: int) -> int:
            value = os.getenv(key)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default
                
        def get_float_env(key: str, default: float) -> float:
            value = os.getenv(key)
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                return default
        
        return cls(
            max_single_file_lines=get_int_env('CODE_REVIEW_MAX_SINGLE_FILE_LINES', 500),
            max_total_diff_lines=get_int_env('CODE_REVIEW_MAX_TOTAL_DIFF_LINES', 1000),
            default_model=os.getenv('CODE_REVIEW_MODEL', "openai/o4-mini"),
            max_tokens=get_int_env('CODE_REVIEW_MAX_TOKENS', 100000),
            temperature=get_float_env('CODE_REVIEW_TEMPERATURE', 0.3),
            glow_style=os.getenv('CODE_REVIEW_GLOW_STYLE', "dracula")
        )
        
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.max_single_file_lines <= 0:
            raise ValueError("max_single_file_lines must be positive")
        if self.max_total_diff_lines <= 0:
            raise ValueError("max_total_diff_lines must be positive")
        if not (0.0 <= self.temperature <= 1.0):
            raise ValueError("temperature must be between 0.0 and 1.0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
    
    def get_summary_prompt_file(self) -> str:
        """Get the path to the summary prompt file.
        
        Returns:
            Path to summary prompt file (summary_prompt.md in project root)
        """
        # Get the project root directory (where this script is located)
        current_file = Path(__file__)
        project_root = current_file.parent.parent
        summary_prompt_path = project_root / "summary_prompt.md"
        
        return str(summary_prompt_path)
