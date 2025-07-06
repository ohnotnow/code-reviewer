#!/usr/bin/env python3
"""
Code Review CLI Tool
A friendly code reviewer powered by Claude for PHP/Laravel projects.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import tempfile

try:
    from litellm import completion
    import litellm
except ImportError:
    print("❌ Error: litellm not installed. Run: pip install litellm")
    sys.exit(1)

# Configuration
MAX_SINGLE_FILE_LINES = 500
MAX_TOTAL_DIFF_LINES = 1000
SUPPORTED_EXTENSIONS = {'.php', '.blade.php'}

SYSTEM_PROMPT = """You are a friendly, experienced PHP/Laravel developer providing code review feedback for a small development team at the University of Glasgow's College of Science and Engineering. The team works on various administrative applications (student placements, risk assessments, research facility management, etc.).

## Your Role & Tone

You're a helpful colleague, not a strict enforcer. Your goal is to help developers write more readable, maintainable code while learning best practices. Be encouraging and constructive - imagine you're the friendly senior developer who always has time to help.

Use a conversational tone with appropriate emoji to make feedback feel approachable:
- ✅ for things done well
- 💡 for suggestions and improvements  
- 🔍 for observations worth noting
- ⚠️ for potential issues or concerns
- 🎯 for particularly good examples of best practices

## Core Principles to Review For

### 1. Readability & Self-Documentation
The primary test: "Could you read this code aloud to a non-programmer and have them understand the gist?"

**Look for:**
- Descriptive variable and function names
- Code that expresses business logic clearly
- Logical flow that's easy to follow

**Flag:**
- Single-letter variables (except standard loop counters)
- Unclear abbreviations
- Functions that do too many things
- Magic numbers without explanation

### 2. Avoiding Magic Strings & Numbers
**Encourage:**
- Class constants for status values
- PHP 8.1+ enums for fixed value sets
- Configuration values for URLs, limits, etc.
- Named constants for important numbers

### 3. Defensive Programming
**Look for and encourage:**
- Early returns to reduce nesting
- Input validation at function boundaries
- Proper error handling
- Null checks where appropriate

**Discourage:**
- Deep nesting with multiple if/else chains
- Assumptions about input data
- Swallowing exceptions silently

### 4. Modern PHP & Laravel Patterns
**Encourage when appropriate:**
- Type declarations on functions
- PHP 8+ features (match expressions, null coalescing assignment)
- Laravel Form Requests for validation
- Eloquent relationships over raw queries
- Service classes for complex business logic
- Laravel Policies for authorization

### 5. Code Organization
**Look for:**
- PSR-12 formatting compliance
- Logical separation of concerns
- Appropriate use of Laravel conventions
- Clear file and class organization

## Review Guidelines

### Response Structure
1. **Start positive** - Acknowledge good patterns you see
2. **Group suggestions** by theme (naming, structure, Laravel patterns, etc.)
3. **Explain the why** - Don't just say what to change, explain the benefit
4. **End encouragingly** - Overall assessment and any particularly good practices

### Example Response Format
```
📝 Code Review Results

✅ Great job using early returns in the validation logic!
✅ Nice work extracting the authorization to a policy - very clean!

💡 **Naming & Clarity**
- Consider renaming `$proj` to `$project` on line 23 - more descriptive

💡 **Laravel Patterns**  
- You might want to use a Form Request for this validation logic

Overall: This code is well-structured and follows good practices. Nice work!
```

Remember: Your goal is to help developers improve while feeling supported, not criticized."""


def run_command(cmd: List[str]) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"


def is_php_file(filepath: str) -> bool:
    """Check if file is a PHP file we should review."""
    path = Path(filepath)
    return path.suffix in SUPPORTED_EXTENSIONS


def count_lines(content: str) -> int:
    """Count non-empty lines in content."""
    return len([line for line in content.split('\n') if line.strip()])


def get_git_changed_files() -> List[str]:
    """Get list of changed files from git status."""
    success, output = run_command(['git', 'status', '--porcelain'])
    
    if not success:
        print(f"❌ Error getting git status: {output}")
        return []
    
    changed_files = []
    for line in output.split('\n'):
        if line.strip():
            # Parse git status output: first two chars are status, rest is filename
            status = line[:2]
            filename = line[3:].strip()
            
            # Skip deleted files
            if 'D' in status:
                continue
                
            # Only include PHP files
            if is_php_file(filename) and Path(filename).exists():
                changed_files.append(filename)
    
    return changed_files


def read_file_content(filepath: str) -> Optional[str]:
    """Read file content, return None if file doesn't exist or can't be read."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        print(f"❌ Error reading {filepath}: {e}")
        return None


def get_git_diff_content(files: List[str]) -> str:
    """Get git diff content for specified files."""
    if not files:
        return ""
    
    success, output = run_command(['git', 'diff', 'HEAD'] + files)
    if not success:
        print(f"⚠️  Warning: Could not get git diff: {output}")
        return ""
    
    return output


def format_single_file_review(filepath: str, content: str) -> str:
    """Format content for single file review."""
    return f"""Please review this PHP file: {filepath}

```php
{content}
```

Please provide a friendly code review focusing on readability, Laravel best practices, and potential improvements."""


def format_diff_review(files: List[str], diff_content: str) -> str:
    """Format content for git diff review."""
    file_list = ", ".join(files)
    return f"""Please review the changes in these files: {file_list}

Here's the git diff showing what has changed:

```diff
{diff_content}
```

Please provide a friendly code review focusing on the changes made, highlighting good practices and suggesting improvements where appropriate."""


def review_code_with_claude(content: str) -> str:
    """Send code to Claude for review."""
    litellm.drop_params = True
    try:
        response = completion(
            model="openai/gpt-4.1",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content}
            ],
            max_tokens=1500,
            temperature=0.3
        )
        
        return str(response.choices[0].message.content)
        
    except Exception as e:
        return f"❌ Error getting review from Claude: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Friendly code review tool powered by Claude",
        epilog="Examples:\n  cr                           # Review changed files\n  cr app/Models/User.php       # Review specific file",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'file', 
        nargs='?', 
        help='Specific file to review (if not provided, reviews git changes)'
    )
    parser.add_argument(
        '--max-lines', 
        type=int, 
        default=MAX_SINGLE_FILE_LINES,
        help=f'Maximum lines for single file review (default: {MAX_SINGLE_FILE_LINES})'
    )
    
    args = parser.parse_args()
    
    # Check for API key
    
    # Check if we're in a git repository
    success, _ = run_command(['git', 'rev-parse', '--git-dir'])
    if not success:
        print("❌ Error: Not in a git repository")
        sys.exit(1)
    
    if args.file:
        # Review specific file
        if not Path(args.file).exists():
            print(f"❌ Error: File {args.file} does not exist")
            sys.exit(1)
        
        if not is_php_file(args.file):
            print(f"❌ Error: {args.file} is not a PHP file")
            sys.exit(1)
        
        content = read_file_content(args.file)
        if content is None:
            sys.exit(1)
        
        line_count = count_lines(content)
        if line_count > args.max_lines:
            response = input(f"⚠️  File has {line_count} lines (max: {args.max_lines}). Continue? [y/N]: ")
            if response.lower() != 'y':
                print("Review cancelled.")
                sys.exit(0)
        
        print(f"🔍 Reviewing {args.file}...")
        review_content = format_single_file_review(args.file, content)
        
    else:
        # Review git changes
        changed_files = get_git_changed_files()
        
        if not changed_files:
            print("✅ No PHP files have been changed.")
            sys.exit(0)
        
        print(f"📁 Found {len(changed_files)} changed PHP file(s): {', '.join(changed_files)}")
        
        # Get diff content and check size
        diff_content = get_git_diff_content(changed_files)
        if diff_content:
            diff_lines = count_lines(diff_content)
            if diff_lines > MAX_TOTAL_DIFF_LINES:
                print(f"⚠️  Large diff detected ({diff_lines} lines). Consider reviewing files individually.")
                response = input("Continue with full diff review? [y/N]: ")
                if response.lower() != 'y':
                    print("Consider reviewing files one at a time with: cr <filename>")
                    sys.exit(0)
        
        print("🔍 Reviewing changes...")
        review_content = format_diff_review(changed_files, diff_content)
    
    # Get review from Claude
    review = review_code_with_claude(review_content)
    
    print("\n" + "="*60)
    print(review)
    print("="*60)


if __name__ == "__main__":
    main()

