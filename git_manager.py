"""
Autonomous GitHub Manager
===========================
Handles git operations: repository initialization, committing, and pushing.
"""

import os
import subprocess
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


def _run_git(*args, cwd="."):
    cmd = ["git"] + list(args)
    logger.debug(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            if "nothing to commit" not in result.stdout + result.stderr:
                logger.warning(f"Git stderr: {result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Git timeout: {' '.join(cmd)}")
    except FileNotFoundError:
        raise RuntimeError("Git is not installed")


def init_repo(repo_dir=".", remote_url=None, github_username="blackmangoo",
             repo_name="AI-agent-job-automation"):
    git_dir = Path(repo_dir) / ".git"
    if not git_dir.exists():
        _run_git("init", cwd=repo_dir)
        _run_git("branch", "-M", "main", cwd=repo_dir)
    if remote_url is None:
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            remote_url = f"https://{token}@github.com/{github_username}/{repo_name}.git"
        else:
            remote_url = f"https://github.com/{github_username}/{repo_name}.git"
    try:
        _run_git("remote", "get-url", "origin", cwd=repo_dir)
        _run_git("remote", "set-url", "origin", remote_url, cwd=repo_dir)
    except RuntimeError:
        _run_git("remote", "add", "origin", remote_url, cwd=repo_dir)


def commit_and_push(message, repo_dir=".", files=None, branch="main"):
    try:
        if files:
            for f in files: _run_git("add", f, cwd=repo_dir)
        else:
            _run_git("add", ".", cwd=repo_dir)
        status = _run_git("status", "--porcelain", cwd=repo_dir)
        if not status:
            logger.info("No changes to commit")
            return True
        _run_git("commit", "-m", message, cwd=repo_dir)
        _run_git("push", "-u", "origin", branch, cwd=repo_dir)
        logger.info(f"Committed and pushed: {message}")
        return True
    except RuntimeError as e:
        logger.error(f"Git operation failed: {e}")
        return False


def create_readme(content, repo_dir="."):
    Path(repo_dir).joinpath("README.md").write_text(content, encoding="utf-8")
    logger.info("README.md updated")
