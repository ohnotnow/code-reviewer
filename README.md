# Code Reviewer

A friendly command-line code review tool for PHP/Laravel projects powered by Claude via the `litellm` library.

Repository: https://github.com/ohnotnow/code-reviewer

## Table of Contents
1. [Features](#features)  
2. [Prerequisites](#prerequisites)  
3. [Installation](#installation)  
4. [Configuration](#configuration)  
5. [Usage](#usage)  
6. [Options & Flags](#options--flags)  
7. [Contributing](#contributing)  
8. [License](#license)  

---

## Features
- Reviews either a single PHP/Blade file or all staged PHP changes in a Git repo  
- Enforces a maximum line count per file or total diff  
- Provides structured, emoji-driven feedback on readability, Laravel best practices, defensive coding, and more  
- Powered by Claude (via `litellm`) with a clear system prompt tuned for PHP/Laravel teams  

---

## Prerequisites
- Git (any recent version)  
- Python 3.8+  
- Claude API access (via `litellm`)  
- [UV CLI tool](https://docs.astral.sh/uv/) installed  

---

## Installation

Clone the repository and install dependencies using the modern `uv` tool.

1. Clone:
   ```bash
   git clone https://github.com/ohnotnow/code-reviewer.git
   cd code-reviewer
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```
   (This reads your `pyproject.toml` / `requirements` and installs `litellm`, etc.)

> If you do not have `uv` installed, follow instructions at https://docs.astral.sh/uv/  

---

## Configuration

This tool requires an API key for Claude (via `litellm`). Set the environment variable before running:

macOS & Ubuntu (bash/zsh):
```bash
export OPENAI_API_KEY="your_api_key_here"
```

Windows CMD:
```cmd
set OPENAI_API_KEY=your_api_key_here
```

Windows PowerShell:
```powershell
$env:OPENAI_API_KEY = "your_api_key_here"
```

---

## Usage

All commands below assume you are in the project root.

1. Review **all staged PHP changes** in your Git repository:
   ```bash
   uv run main.py
   ```
   or, if `main.py` has execute permissions:
   ```bash
   ./main.py
   ```

2. Review a **single file**:
   ```bash
   uv run main.py path/to/File.php
   ```

---

## Options & Flags

- `--max-lines <n>`  
  Maximum non-empty lines allowed for a single-file review (default: 500).

- `-h, --help`  
  Show help message and exit.

### Examples

Review changed files with a higher single-file limit:
```bash
uv run main.py --max-lines 800
```

Review one file:
```bash
uv run main.py app/Models/User.php
```

---

## Contributing

1. Fork the repository  
2. Create a feature branch: `git checkout -b feature/your-feature`  
3. Commit your changes and push: `git push origin feature/your-feature`  
4. Open a pull request describing your changes

Please adhere to existing code style and update this README if you introduce new functionality.

---

## License

This project is licensed under the MIT License.  
See [LICENSE](LICENSE) for details.
