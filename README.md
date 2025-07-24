# Code Reviewer

A friendly command-line code review tool for projects powered by an LLM.

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
- Reviews either a single file or all changes in a Git repo
- Enforces a maximum line count per file or total diff
- Provides structured, emoji-driven feedback on readability, best practices, defensive coding, and more
- Powered by an LLM (via `litellm`) with a clear system prompt tuned for practical teams

---

## Prerequisites
- Git (any recent version)
- Python 3.8+
- LLM API access (via `litellm`)
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

This tool requires an API key for your LLM. Set the environment variable before running:

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

All commands below assume you are in the PHP projects root.

1. Review **all staged PHP changes** in your Git repository:
   ```bash
   source /path/to/code-reviewer/.venv/bin/activate
   uv run /path/to/code-reviewer/main.py
   deactivate
   ```

2. Review a **single file**:
   ```bash
   source /path/to/code-reviewer/.venv/bin/activate
   uv run /path/to/code-reviewer/main.py path/to/File.php
   deactivate
   ```

Note: by default it will just print the markdown report to your terminal.  If you have the [glow](https://github.com/charmbracelet/glow) utility installed it will 'render' the markdown instead.

If you find yourself frequently using this tool, you can add it to your `.bashrc` or `.zshrc` file:

```bash
cr() {
    source /path/to/code-reviewer/.venv/bin/activate
    python /path/to/code-reviewer/main.py "$*"
    deactivate
}
```
---

## Options & Flags

- `--max-lines <n>`
  Maximum non-empty lines allowed for a single-file review (default: 500).

- `-h, --help`
  Show help message and exit.

- `--model <model_name>`
  Model name to use for the LLM (default: `openai/o4-mini`).

- `--prompt-file <specific-prompt.md>`
  Use a specific code-review prompt file for this run.  This can also be handy to set up aliases where you pass a specific prompt for, say, golang/python/typescript etc.

- `--since-commit <commit-hash>`
  Compare against the current commit and another specific commit.

## Style Guide

The script looks for a file called `~/.code-review-prompt.md` for its instructions.  If it isn't found it will default to the `system_prompt.md` file in the repo.  You can copy the default file to `~/.code-review-prompt.md` and edit it to suit your preferences.


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
