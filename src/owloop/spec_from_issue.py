"""Convert a GitHub issue into an owloop spec draft."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from owloop.paths import resolve_specs_dir, resolve_templates_dir


class IssueToSpecConverter:
    """Fetch a GitHub issue and render it as an owloop spec."""

    def __init__(self, project_dir: Path) -> None:
        """Initialize with the project root directory.

        Args:
            project_dir: Root of the consumer project (where specs/ and
                templates/ live).
        """
        self.project_dir = Path(project_dir)
        self.specs_dir = resolve_specs_dir(self.project_dir)
        self.template_path = resolve_templates_dir(self.project_dir) / "spec-template.md"

    def from_github(self, issue_url_or_number: str, repo: str | None = None) -> dict[str, str]:
        """Fetch a GitHub issue and return structured spec data.

        Args:
            issue_url_or_number: Full GitHub issue URL or just the issue number.
            repo: Optional "owner/repo" override. Required when only a number
                is supplied and the repo cannot be inferred from git remotes.

        Returns:
            Dictionary with string values suitable for spec rendering:
            ``title``, ``body``, ``number``, ``state``, ``requirements``,
            ``acceptance_criteria``.

        Raises:
            ValueError: If the issue reference is invalid or the repo cannot be
                determined.
            RuntimeError: If the issue cannot be fetched because of missing
                tooling, network issues, or a 404 response.
        """
        owner, repo_name, number = self._parse_issue(issue_url_or_number, repo)
        data = self._fetch_issue(owner, repo_name, number)
        body = data.get("body") or ""
        requirements, criteria = self._parse_issue_body(body)
        return {
            "title": data.get("title", ""),
            "body": body,
            "number": str(data.get("number", number)),
            "state": data.get("state", "unknown"),
            "requirements": requirements,
            "acceptance_criteria": criteria,
        }

    def render_spec(self, data: dict[str, str]) -> str:
        """Render the spec template with the supplied issue data.

        Args:
            data: Issue data as returned by :meth:`from_github`.

        Returns:
            Rendered spec markdown.

        Raises:
            FileNotFoundError: If ``templates/spec-template.md`` is missing.
        """
        if not self.template_path.is_file():
            raise FileNotFoundError(f"Spec template not found: {self.template_path}")

        template = self.template_path.read_text(encoding="utf-8")
        return self._render_template(template, data)

    def write_spec(
        self,
        data: dict[str, str],
        output_path: Path | None = None,
    ) -> Path:
        """Write a rendered spec to disk.

        Args:
            data: Issue data as returned by :meth:`from_github`.
            output_path: Optional explicit output path. When omitted, the spec
                is written to ``specs/{next}-{slug}.md``.

        Returns:
            Path to the written spec file.
        """
        rendered = self.render_spec(data)

        if output_path is not None:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            return output_path

        number = self._next_spec_number()
        title_slug = self._slugify(data.get("title", "spec"))
        filename = f"{number:03d}-{title_slug}.md"
        spec_path = self.specs_dir / filename
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(rendered, encoding="utf-8")
        return spec_path

    def from_jira(self, issue_key: str, base_url: str | None = None) -> dict[str, str]:
        """Stub for future Jira support.

        Args:
            issue_key: Jira issue key.
            base_url: Optional Jira instance base URL.

        Raises:
            NotImplementedError: Always, until Jira support is implemented.
        """
        raise NotImplementedError(
            "Jira issue import is not yet implemented. "
            "Use from_github() for GitHub issues."
        )

    def _parse_issue(self, issue: str, repo: str | None = None) -> tuple[str, str, int]:
        """Resolve an issue reference into (owner, repo, number)."""
        issue = issue.strip()

        url_match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)(?:\?.*)?$",
            issue,
            re.IGNORECASE,
        )
        if url_match:
            return url_match.group(1), url_match.group(2), int(url_match.group(3))

        if issue.isdigit():
            number = int(issue)
            owner_repo = repo or self._infer_repo()
            if not owner_repo:
                raise ValueError(
                    "Could not determine GitHub repository. "
                    "Use --repo owner/repo or run inside a git repo with a GitHub remote."
                )
            if "/" not in owner_repo:
                raise ValueError(
                    f"Invalid repository '{owner_repo}'. Expected format: owner/repo."
                )
            owner, repo_name = owner_repo.split("/", 1)
            return owner, repo_name, number

        raise ValueError(
            f"Invalid issue reference: {issue!r}. "
            "Expected a GitHub issue URL or a numeric issue ID."
        )

    def _infer_repo(self) -> str | None:
        """Try to read ``owner/repo`` from the local git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

        url = result.stdout.strip()

        ssh_match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
        if ssh_match:
            return f"{ssh_match.group(1)}/{ssh_match.group(2)}"

        https_match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:\?.*)?$", url
        )
        if https_match:
            return f"{https_match.group(1)}/{https_match.group(2)}"

        return None

    def _fetch_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """Fetch issue JSON, preferring ``gh`` and falling back to requests."""
        if shutil.which("gh"):
            return self._fetch_with_gh(owner, repo, number)
        return self._fetch_with_requests(owner, repo, number)

    def _fetch_with_gh(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """Fetch issue data using the GitHub CLI."""
        cmd = [
            "gh",
            "issue",
            "view",
            str(number),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "title,body,number,state",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip()
            if "HTTP 404" in stderr or "Could not resolve to an issue" in stderr:
                raise RuntimeError(
                    f"Issue #{number} not found in {owner}/{repo}."
                ) from exc
            raise RuntimeError(
                f"Failed to fetch issue #{number} from {owner}/{repo}: {stderr or exc.stdout}"
            ) from exc

        try:
            data: dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Unexpected output from 'gh issue view': {result.stdout!r}"
            ) from exc
        return data

    def _fetch_with_requests(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """Fetch issue data using the public GitHub REST API."""
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "GitHub CLI ('gh') not found and the 'requests' package is not installed. "
                "Install one of them to fetch issues."
            ) from exc

        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
        try:
            response = requests.get(url, timeout=30)
        except Exception as exc:
            raise RuntimeError(f"Network error fetching issue #{number}: {exc}") from exc

        if response.status_code == 404:
            raise RuntimeError(f"Issue #{number} not found in {owner}/{repo}.")
        try:
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"GitHub API error for issue #{number}: {response.status_code} {response.text}"
            ) from exc

        data: dict[str, Any] = response.json()
        return data

    def _parse_issue_body(self, body: str) -> tuple[str, str]:
        """Split an issue body into requirements text and acceptance criteria.

        Checklist items become candidate acceptance criteria. Non-checklist
        content is preserved as the Requirements section.
        """
        requirement_lines: list[str] = []
        criteria: list[str] = []

        for line in body.splitlines():
            stripped = line.strip()
            match = re.match(r"^(?:[-*]|\d+\.)\s+\[[xX ]\]\s+(.*)$", stripped)
            if match:
                criteria.append(match.group(1))
                continue
            requirement_lines.append(line)

        requirements = "\n".join(requirement_lines).strip()
        if not requirements:
            requirements = "TODO: describe what needs to be done"

        if criteria:
            criteria_text = "\n".join(f"- [ ] {item}" for item in criteria)
        else:
            criteria_text = "- [ ] TODO: shell command → expected output"

        return requirements, criteria_text

    def _render_template(self, template: str, data: dict[str, str]) -> str:
        """Substitute issue data into the spec template."""
        title = data.get("title", "")
        requirements = data.get("requirements", "TODO: describe what needs to be done")
        criteria = data.get("acceptance_criteria", "- [ ] TODO: shell command → expected output")

        rendered = template.replace("[name]", title)
        rendered = rendered.replace("[1-5]", "3")

        rendered = self._replace_section(rendered, "Requirements", requirements.rstrip() + "\n")
        rendered = self._replace_section(
            rendered,
            "Acceptance Criteria",
            "Candidate acceptance criteria derived from issue checklist items:\n\n"
            + criteria.rstrip()
            + "\n",
        )

        return rendered

    def _replace_section(self, content: str, section: str, new_content: str) -> str:
        """Replace the body of a ``## Section`` with new markdown."""
        pattern = re.compile(
            rf"^(## {re.escape(section)}\n)(.*?)(?=^## |\Z)",
            re.MULTILINE | re.DOTALL,
        )

        def replacer(match: re.Match[str]) -> str:
            return f"{match.group(1)}{new_content}\n"

        return pattern.sub(replacer, content)

    def _next_spec_number(self) -> int:
        """Return the next available spec number based on existing specs."""
        if not self.specs_dir.is_dir():
            return 1

        max_number = 0
        for path in self.specs_dir.glob("*.md"):
            match = re.match(r"^(\d+)-", path.name)
            if match:
                max_number = max(max_number, int(match.group(1)))
        return max_number + 1

    @staticmethod
    def _slugify(text: str) -> str:
        """Create a URL-friendly slug from arbitrary text."""
        slug = text.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug.strip("-")[:50]
