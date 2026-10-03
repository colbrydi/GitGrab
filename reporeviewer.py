"""
reporeviewer - A lightweight module to scan and report on local Git repositories.
"""

from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional, Union


class RepoStatus:
    """Encapsulates the status and metadata of a single Git repository."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.name = self.path.name
        self.branch: str = "Unknown"
        self.is_default_branch: bool = False
        self.has_uncommitted: bool = False
        self.has_untracked: bool = False
        self.unpushed_commits: int = 0
        self.unpulled_commits: int = 0
        self.remote_url: str = ""
        self.web_url: str = ""
        self.last_commit_date: str = ""
        self.last_commit_msg: str = ""
        self.is_git_repo: bool = False

        self._check_if_git_repo()
        if self.is_git_repo:
            self.refresh()

    def _run_git(self, args: List[str]) -> Optional[str]:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=self.path,
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _check_if_git_repo(self) -> None:
        git_dir = self.path / ".git"
        self.is_git_repo = git_dir.exists()

    def refresh(self, fetch: bool = False) -> None:
        if not self.is_git_repo:
            return

        if fetch:
            self._run_git(["fetch", "--quiet"])

        self._get_branch_info()
        self._get_status_flags()
        self._get_remote_and_web_url()
        self._get_commit_counts()
        self._get_last_commit_info()
        self.description = self._get_description()

    def _get_branch_info(self) -> None:
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        self.branch = branch if branch else "Detached HEAD"
        self.is_default_branch = self.branch in ["main", "master"]

    def _get_status_flags(self) -> None:
        status_output = self._run_git(["status", "--porcelain"])
        if status_output is None:
            return

        lines = status_output.splitlines() if status_output else []
        self.has_untracked = any(line.startswith("??") for line in lines)
        self.has_uncommitted = any(not line.startswith("??") for line in lines)

    def _get_remote_and_web_url(self) -> None:
        raw_url = self._run_git(["config", "--get", "remote.origin.url"]) or ""
        self.remote_url = raw_url

        if raw_url.startswith("git@"):
            web = re.sub(r"^git@([^:]+):", r"https://\1/", raw_url)
            web = re.sub(r"\.git$", "", web)
            self.web_url = web
        elif raw_url.startswith("http"):
            self.web_url = re.sub(r"\.git$", "", raw_url)
        else:
            self.web_url = raw_url

    def _get_commit_counts(self) -> None:
        counts = self._run_git(
            ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]
        )
        if counts:
            parts = counts.split()
            if len(parts) == 2:
                self.unpushed_commits = int(parts[0])
                self.unpulled_commits = int(parts[1])

    def _get_last_commit_info(self) -> None:
        log_out = self._run_git(["log", "-1", "--format=%cd|%s", "--date=short"])
        if log_out and "|" in log_out:
            date_str, msg = log_out.split("|", 1)
            self.last_commit_date = date_str
            self.last_commit_msg = msg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "web_url": self.web_url,
            "path": str(self.path),
            "branch": self.branch,
            "is_default_branch": self.is_default_branch,
            "has_uncommitted": self.has_uncommitted,
            "has_untracked": self.has_untracked,
            "unpushed_commits": self.unpushed_commits,
            "unpulled_commits": self.unpulled_commits,
            "remote_url": self.remote_url,
            "last_commit_date": self.last_commit_date,
            "last_commit_msg": self.last_commit_msg,
        }
        
    def _get_description(self) -> str:
        """Reads the repository description from .git/description if available."""
        desc_file = self.path / ".git" / "description"
        if desc_file.is_file():
            try:
                content = desc_file.read_text(encoding="utf-8").strip()
                # Filter out default Git placeholder
                if content and not content.startswith("Unnamed repository;"):
                    return content
            except Exception:
                pass
        return ""


def getrepos(
    root_dir: str = ".", fetch: bool = False, as_dict: bool = True
) -> Dict[str, Any]:
    """Scans subdirectories in root_dir for Git repos and returns their statuses."""
    root = Path(root_dir).resolve()
    results = {}

    for item in root.iterdir():
        if item.is_dir():
            repo = RepoStatus(item)
            if repo.is_git_repo:
                if fetch:
                    repo.refresh(fetch=True)
                results[item.name] = repo.to_dict() if as_dict else repo

    return results


def _is_repo_dict(d: Dict[str, Any]) -> bool:
    """Check if a dictionary represents a single repository's attributes."""
    expected_keys = {"branch", "has_uncommitted", "has_untracked"}
    return expected_keys.issubset(d.keys())


def to_markdown(
    data: Dict[str, Any], name: Optional[str] = None, depth: int = 0
) -> str:
    """Recursively converts a repo dict or nested dict of repos into Markdown.

    Args:
        data: A single repo dictionary OR a dictionary mapping names to repo
          dicts.
        name: Name to print for a single repo section (optional).
        depth: Indentation depth for nested dictionaries (used in recursion).

    Returns:
        A Markdown-formatted string representation.
    """
    lines: List[str] = []
    indent = "  " * depth

    # Case 1: Single Repository Dictionary
    if _is_repo_dict(data):
        repo_title = name or Path(data.get("path", "Repository")).name
        web_url = data.get("web_url", "")

        # Format Title with Clickable Link if available
        if web_url:
            lines.append(f"{indent}* **[{repo_title}]({web_url})**")
        else:
            lines.append(f"{indent}* **{repo_title}**")

        # Determine Sync & Local Status
        unpushed = data.get("unpushed_commits", 0)
        unpulled = data.get("unpulled_commits", 0)
        has_uncommitted = data.get("has_uncommitted", False)
        has_untracked = data.get("has_untracked", False)
        branch = data.get("branch", "unknown")

        status_notes = []
        if not data.get("is_default_branch", True):
            status_notes.append(f"Branch: `{branch}`")

        if has_uncommitted or has_untracked:
            local_flags = []
            if has_uncommitted:
                local_flags.append("uncommitted changes")
            if has_untracked:
                local_flags.append("untracked files")
            status_notes.append(f"Local: {', '.join(local_flags)}")
        else:
            status_notes.append("Local: clean")

        if unpushed == 0 and unpulled == 0:
            status_notes.append("Sync: up to date")
        else:
            sync_flags = []
            if unpushed > 0:
                sync_flags.append(f"{unpushed} ahead")
            if unpulled > 0:
                sync_flags.append(f"{unpulled} behind")
            status_notes.append(f"Sync: {', '.join(sync_flags)}")

        lines.append(f"{indent}  * Status: {' | '.join(status_notes)}")

        desc = data.get("description", "")
        if desc:
            lines.append(f"{indent}  * _{desc}_")
        else:
            lines.append(f"{indent}  * _No Description_")
            
        return "\n".join(lines)

    # Case 2: Dictionary of Repositories (or nested structures)
    for key, value in data.items():
        if isinstance(value, dict):
            if _is_repo_dict(value):
                lines.append(to_markdown(value, name=key, depth=depth))
            else:
                # Optional nested group header
                lines.append(f"{indent}### {key}")
                lines.append(to_markdown(value, depth=depth + 1))

    return "\n".join(lines)

# Helper function to check if a repo needs attention
def needs_attention(repo: dict) -> bool:
  has_local_changes = repo["has_uncommitted"] or repo["has_untracked"]
  has_sync_issues = (repo["unpushed_commits"] > 0) or (
      repo["unpulled_commits"] > 0
  )
  off_default_branch = not repo.get("is_default_branch", True)

  return has_local_changes or has_sync_issues or off_default_branch