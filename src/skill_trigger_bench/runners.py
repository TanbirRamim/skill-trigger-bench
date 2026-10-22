"""Runners execute one prompt in a sandbox and return a parsed transcript.

To add an agent (Codex, Gemini CLI, ...), subclass Runner, implement `run`, and
register it in RUNNERS.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .skills import load_skill
from .stream import Transcript, parse_codex_text, parse_gemini_text, parse_text


class RunnerError(RuntimeError):
    pass


@dataclass
class Runner:
    model: str | None = None
    timeout: int = 180
    extra_args: list[str] = field(default_factory=list)
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def run(self, prompt: str, skill_dirs: list[Path]) -> Transcript:
        raise NotImplementedError

    @staticmethod
    def make_sandbox(skill_dirs: list[Path], layout: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="stb-"))
        dest = root / layout
        dest.mkdir(parents=True)
        for d in skill_dirs:
            shutil.copytree(d, dest / d.name, symlinks=False, dirs_exist_ok=True)
        return root


# Tools that could change anything or cost a lot are turned off; the run only needs
# to show whether the model reaches for the Skill tool.
CLAUDE_BLOCKED_TOOLS = [
    "Bash",
    "Edit",
    "Write",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "Task",
    "Agent",
]


@dataclass
class ClaudeRunner(Runner):
    binary: str = "claude"
    max_turns: int = 2
    name = "claude"

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def command(self, prompt: str) -> list[str]:
        cmd = [
            self.binary,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--max-turns",
            str(self.max_turns),
            # only the sandbox project's settings and skills; ignores ~/.claude skills and plugins
            "--setting-sources",
            "project",
            "--disallowedTools",
            ",".join(CLAUDE_BLOCKED_TOOLS),
        ]
        if self.model:
            cmd += ["--model", self.model]
        return cmd + self.extra_args

    def run(self, prompt: str, skill_dirs: list[Path]) -> Transcript:
        sandbox = self.make_sandbox(skill_dirs, ".claude/skills")
        try:
            proc = subprocess.run(
                self.command(prompt),
                cwd=sandbox,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as e:
            raise RunnerError(f"claude timed out after {self.timeout}s") from e
        except OSError as e:
            raise RunnerError(f"could not start {self.binary}: {e}") from e
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        t = parse_text(proc.stdout)
        if t.is_error or (proc.returncode != 0 and not t.finished):
            raise RunnerError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:300]}")
        return t


@dataclass
class CodexRunner(Runner):
    """OpenAI Codex CLI (`codex exec --json`).

    Skills go in <sandbox>/.agents/skills, the repository scope Codex scans from the working
    directory. HOME is pointed at the sandbox so $HOME/.agents/skills is empty, while
    CODEX_HOME keeps the real one so auth still works. Admin (/etc/codex/skills) and
    bundled system skills can't be turned off from here and stay visible.

    Codex emits no "skill used" event, so activation is a heuristic: a shell command that
    reads <skill>/SKILL.md. See stream.parse_codex_events.
    """

    binary: str = "codex"
    name = "codex"

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def command(self, prompt: str, sandbox: Path) -> list[str]:
        cmd = [
            self.binary,
            "exec",
            "--json",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--cd",
            str(sandbox),
            "-c",
            'web_search="disabled"',
            "-c",
            'approval_policy="never"',
        ]
        if self.model:
            cmd += ["--model", self.model]
        return cmd + self.extra_args + ["--", prompt]

    def env(self, sandbox: Path) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
        env["HOME"] = str(sandbox)
        return env

    def run(self, prompt: str, skill_dirs: list[Path]) -> Transcript:
        names = {}
        for d in skill_dirs:
            try:
                names[d.name] = load_skill(d / "SKILL.md").name
            except (OSError, ValueError):
                names[d.name] = d.name
        sandbox = self.make_sandbox(skill_dirs, ".agents/skills")
        try:
            proc = subprocess.run(
                self.command(prompt, sandbox),
                cwd=sandbox,
                env=self.env(sandbox),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as e:
            raise RunnerError(f"codex timed out after {self.timeout}s") from e
        except OSError as e:
            raise RunnerError(f"could not start {self.binary}: {e}") from e
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        t = parse_codex_text(proc.stdout, names)
        if t.is_error or (proc.returncode != 0 and not t.finished):
            detail = t.result or proc.stderr.strip()
            raise RunnerError(f"codex exited {proc.returncode}: {detail[:300]}")
        return t


@dataclass
class GeminiRunner(Runner):
    """Google Gemini CLI (`gemini -p`).

    Skills go in <sandbox>/.gemini/skills. The runner sets GEMINI_CLI_HOME to the sandbox
    (the CLI reads <GEMINI_CLI_HOME>/.gemini instead of ~/.gemini) so global user-level
    skills do not leak in.
    """

    binary: str = "gemini"
    name: str = "gemini"

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def command(self, prompt: str) -> list[str]:
        cmd = [
            self.binary,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
        ]
        if self.model:
            cmd += ["--model", self.model]
        return cmd + self.extra_args

    def env(self, sandbox: Path) -> dict[str, str]:
        env = dict(os.environ)
        env["GEMINI_CLI_HOME"] = str(sandbox)
        return env

    def run(self, prompt: str, skill_dirs: list[Path]) -> Transcript:
        names = {}
        for d in skill_dirs:
            try:
                names[d.name] = load_skill(d / "SKILL.md").name
            except (OSError, ValueError):
                names[d.name] = d.name
        sandbox = self.make_sandbox(skill_dirs, ".gemini/skills")
        try:
            proc = subprocess.run(
                self.command(prompt),
                cwd=sandbox,
                env=self.env(sandbox),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as e:
            raise RunnerError(f"gemini timed out after {self.timeout}s") from e
        except OSError as e:
            raise RunnerError(f"could not start {self.binary}: {e}") from e
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        t = parse_gemini_text(proc.stdout, names)
        if t.is_error or (proc.returncode != 0 and not t.finished):
            detail = t.result or proc.stderr.strip()
            raise RunnerError(f"gemini exited {proc.returncode}: {detail[:300]}")
        return t


@dataclass
class ReplayRunner(Runner):
    """Replays recorded transcripts; used by tests and for offline re-scoring."""

    transcripts: list[str] = field(default_factory=list)
    name = "replay"

    def available(self) -> bool:
        return True

    def run(self, prompt: str, skill_dirs: list[Path]) -> Transcript:
        if not self.transcripts:
            raise RunnerError("replay runner ran out of transcripts")
        return parse_text(self.transcripts.pop(0))


RUNNERS: dict[str, type[Runner]] = {
    "claude": ClaudeRunner,
    "codex": CodexRunner,
    "gemini": GeminiRunner,
}
