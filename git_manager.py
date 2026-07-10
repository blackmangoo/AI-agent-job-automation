"""
Autonomous GitHub Manager
===========================
Handles git operations: repository initialization, committing changes,
and pushing to GitHub. Uses subprocess for git commands.

This module is designed to be used both during development (auto-commit
after each module) and during runtime (commit application logs).
"""

import os
import subprocess
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


def _run_git(*args, cwd: str = ".") -> str:
    """Run a git command and return its output.

    Args:
        *args: Git command arguments (e.g., "add", ".").
        cwd: Working directory for the command.

    Returns:
        Command stdout as a string.

    Raises:
        RuntimeError: If the git command fails.
    """
    cmd = ["git"] + list(args)
    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Some commands (like status) return non-zero for expected states
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                return result.stdout
            logger.warning(f"Git command stderr: {result.stderr.strip()}")

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Git command timed out: {' '.join(cmd)}")
    except FileNotFoundError:
        raise RuntimeError("Git is not installed or not in PATH")


def init_repo(
    repo_dir: str = ".",
    remote_url: str = None,
    github_username: str = "blackmangoo",
    repo_name: str = "AI-agent-job-automation",
) -> None:
    """Initialize a local git repository and configure remote.

    If the repo is already initialized, skips initialization.
    If a remote already exists, updates it.

    Args:
        repo_dir: Path to the repository directory.
        remote_url: Full remote URL. If None, constructs from username/repo_name.
        github_username: GitHub username for constructing remote URL.
        repo_name: Repository name for constructing remote URL.
    """
    git_dir = Path(repo_dir) / ".git"

    if not git_dir.exists():
        logger.info(f"Initializing git repository in {repo_dir}")
        _run_git("init", cwd=repo_dir)
        _run_git("branch", "-M", "main", cwd=repo_dir)
    else:
        logger.info("Git repository already initialized")

    # Configure remote
    if remote_url is None:
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            remote_url = f"https://{token}@github.com/{github_username}/{repo_name}.git"
        else:
            remote_url = f"https://github.com/{github_username}/{repo_name}.git"

    try:
        existing_remote = _run_git("remote", "get-url", "origin", cwd=repo_dir)
        if existing_remote != remote_url:
            _run_git("remote", "set-url", "origin", remote_url, cwd=repo_dir)
            logger.info("Updated remote origin URL")
    except RuntimeError:
        _run_git("remote", "add", "origin", remote_url, cwd=repo_dir)
        logger.info(f"Added remote origin: {remote_url.replace(os.getenv('GITHUB_TOKEN', ''), '***')}")


def commit_and_push(
    message: str,
    repo_dir: str = ".",
    files: list = None,
    branch: str = "main",
) -> bool:
    """Stage, commit, and push changes to GitHub.

    Args:
        message: Commit message (e.g., "feat: add scraper module").
        repo_dir: Path to the repository directory.
        files: Specific files to stage. If None, stages all changes.
        branch: Branch to push to. Defaults to "main".

    Returns:
        True if commit and push succeeded, False otherwise.
    """
    try:
        # Stage changes
        if files:
            for f in files:
                _run_git("add", f, cwd=repo_dir)
            logger.debug(f"Staged {len(files)} specific files")
        else:
            _run_git("add", ".", cwd=repo_dir)
            logger.debug("Staged all changes")

        # Check if there are changes to commit
        status = _run_git("status", "--porcelain", cwd=repo_dir)
        if not status:
            logger.info("No changes to commit")
            return True

        # Commit
        _run_git("commit", "-m", message, cwd=repo_dir)
        logger.info(f"Committed: {message}")

        # Push
        _run_git("push", "-u", "origin", branch, cwd=repo_dir)
        logger.info(f"Pushed to origin/{branch}")

        return True

    except RuntimeError as e:
        logger.error(f"Git operation failed: {e}")
        return False


def create_readme(content: str, repo_dir: str = ".") -> None:
    """Create or update the README.md file.

    Args:
        content: Full README content in Markdown format.
        repo_dir: Path to the repository directory.
    """
    readme_path = Path(repo_dir) / "README.md"
    readme_path.write_text(content, encoding="utf-8")
    logger.info("README.md created/updated")
