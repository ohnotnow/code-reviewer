"""
Core LLM review functionality for the code reviewer.
"""

import logging
from typing import Optional

import litellm
from litellm import completion, completion_cost

from .config import Config
from .exceptions import FileError, LLMError
from .file_utils import get_system_prompt


class CodeReviewer:
    """Core code review functionality.
    
    Attributes:
        config: Configuration instance
        logger: Logger for debugging review operations
    """
    
    def __init__(self, config: Config, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger('codereviewer')
        
    def get_review(self, content: str, model: Optional[str] = None, 
                  prompt_file: Optional[str] = None, debug: bool = False) -> str:
        """Send code to LLM for review.
        
        Args:
            content: Code content to review
            model: LLM model to use (optional)
            prompt_file: Custom prompt file (optional)
            debug: Enable debug output
            
        Returns:
            Review response from LLM
            
        Raises:
            FileError: If prompt file cannot be read
            LLMError: If LLM API call fails
        """
        try:
            system_prompt = get_system_prompt(prompt_file, self.logger)
        except FileError:
            # Re-raise file errors as-is
            raise
        
        model_to_use = model or self.config.default_model
        self.logger.debug(f"Sending review request to {model_to_use}")
        self.logger.debug(f"Content length: {len(content)} characters")
        
        # Check if content is too large based on token estimation
        estimated_tokens = len(content + system_prompt) // self.config.token_estimate_chars_per_token
        if estimated_tokens > self.config.max_estimated_tokens:
            raise LLMError(f"Content too large ({estimated_tokens:,} estimated tokens). Consider reviewing smaller chunks or individual files.")
        
        litellm.drop_params = True
        if debug:
            litellm._turn_on_debug()  # Enable LiteLLM debugging
            self.logger.debug("="*60)
            self.logger.debug(f"SYSTEM PROMPT: {system_prompt}")
            self.logger.debug("="*60)
            self.logger.debug(f"CONTENT: {content}")
            self.logger.debug("="*60)
            
        try:
            response = completion(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )

            # Extract response content
            if not hasattr(response, 'choices') or not response.choices:
                self.logger.debug(f"LLM response object: {response}")
                raise LLMError("LLM response has no choices")
                
            cost = completion_cost(response)
            formatted_cost = f"US${cost:.4f}"
            self.logger.debug(f"LLM response cost: {formatted_cost}")

            choice = response.choices[0]
            if not hasattr(choice, 'message') or not hasattr(choice.message, 'content'):
                self.logger.debug(f"Choice object: {choice}")
                raise LLMError("LLM response has invalid structure")
                
            # Check if response was truncated due to token limits
            if hasattr(choice, 'finish_reason') and choice.finish_reason == 'length':
                self.logger.warning(f"LLM response was truncated due to token limit. Used {self.config.max_tokens} tokens.")
                raise LLMError(f"LLM response was truncated due to {self.config.max_tokens} token limit. Try using --max-lines with a smaller value or increase max_tokens in config.")
                
            content_value = choice.message.content
            self.logger.debug(f"Raw content value: {repr(content_value)}")
            
            if content_value is None:
                # Sometimes models return None content for various reasons
                self.logger.warning("LLM returned None content - possibly due to content filters or token limits")
                raise LLMError("LLM returned empty content (None). This may be due to content size, filters, or model limits.")
                
            review_content = str(content_value).strip()
            if not review_content:
                # Check if this is due to finish_reason being 'length'
                if hasattr(choice, 'finish_reason') and choice.finish_reason == 'length':
                    raise LLMError(f"LLM hit the {self.config.max_tokens} token limit and returned empty content. Try reducing file size or increasing max_tokens.")
                self.logger.warning(f"LLM returned empty string content. Raw value was: {repr(content_value)}")
                raise LLMError("LLM response content is empty after processing")
                
            self.logger.debug(f"Received review response ({len(review_content)} characters)")
            review_content = f"{review_content}\n\nModel: {model_to_use} -- Cost: {formatted_cost}\n"
            return review_content

        except Exception as e:
            self.logger.error(f"LLM API call failed: {e}")
            raise LLMError(f"Error getting review from LLM: {e}")
