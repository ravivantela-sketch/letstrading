"""Local secret scanner for Git hooks.

Scans staged or tracked Git content for likely credentials and blocks the
operation when a suspicious value is found.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDERS = {
    "",
    "your_api_key_here",
    "your_api_secret_here",
    "your_access_token_here",
    "your_telegram_bot_token_here",
    "your_chat_id_here",
    "http://127.0.0.1:5000/callback",
    "paper",
    "live",
}
SENSITIVE_ENV_NAMES = {
    "UPSTOX_API_KEY",
    "UPSTOX_API_SECRET",
    "UPSTOX_ACCESS_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
}
TEXT_SUFFIXES = {
    ".env",
    ".example",
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".ini",
    ".cfg",
    ".toml",
}


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def list_files(mode: str) -> list[str]:
    if mode == "staged":
        output = run_git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    elif mode == "head":
        output = run_git("ls-files")
    else:
        raise ValueError(f"Unsupported mode: {mode}")
    return [line.strip() for line in output.splitlines() if line.strip()]


def is_text_candidate(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    name = Path(path).name.lower()
    if name == ".env" or name.endswith(".env"):
        return True
    return suffix in TEXT_SUFFIXES or path.endswith(".env.example")


def read_file_content(path: str, mode: str) -> str:
    if mode == "staged":
        result = subprocess.run(
            ["git", "show", f":{path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return ""
        return result.stdout

    if mode == "head":
        result = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return result.stdout

    file_path = REPO_ROOT / path
    if not file_path.exists() or file_path.is_dir():
        return ""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def clean_value(raw_value: str) -> str:
    value = raw_value.strip().strip('"').strip("'")
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    return value


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in PLACEHOLDERS or lowered.startswith("your_")


def looks_like_secret(name: str, value: str) -> bool:
    if not value or is_placeholder(value):
        return False

    if name in SENSITIVE_ENV_NAMES:
        return True

    generic_names = (
        "token",
        "secret",
        "api_key",
        "access_token",
        "chat_id",
    )
    lowered_name = name.lower()
    if any(part in lowered_name for part in generic_names) and len(value) >= 8:
        return True

    return False


def find_findings(path: str, content: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    env_assignment = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$")
    code_assignment = re.compile(
        r"(?i)(access[_-]?token|api[_-]?key|api[_-]?secret|bot[_-]?token|chat[_-]?id)\s*[:=]\s*(['\"])([^'\"]+)\2"
    )
    telegram_token = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b")
    jwt_token = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
    is_env_file = path.endswith(".env") or path.endswith(".env.example") or Path(path).suffix.lower() == ".example"

    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        env_match = env_assignment.match(line)
        if is_env_file and env_match:
            name = env_match.group(1)
            value = clean_value(env_match.group(2))
            if looks_like_secret(name, value):
                findings.append((line_no, f"sensitive assignment: {name}"))
                continue

        for name, _, value in code_assignment.findall(line):
            cleaned = clean_value(value)
            if looks_like_secret(name, cleaned):
                findings.append((line_no, f"inline credential: {name}"))
                break

        if telegram_token.search(line):
            findings.append((line_no, "telegram bot token pattern"))
            continue

        if jwt_token.search(line):
            findings.append((line_no, "jwt token pattern"))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Git content for likely secrets.")
    parser.add_argument("--mode", choices=["staged", "head"], default="staged")
    args = parser.parse_args()

    findings: list[tuple[str, int, str]] = []
    for path in list_files(args.mode):
        if not is_text_candidate(path):
            continue
        content = read_file_content(path, args.mode)
        if not content:
            continue
        for line_no, reason in find_findings(path, content):
            findings.append((path, line_no, reason))

    if not findings:
        print(f"Secret scan passed for {args.mode} content.")
        return 0

    print("Secret scan blocked this Git action. Review the following redacted findings:")
    for path, line_no, reason in findings:
        print(f"  - {path}:{line_no} -> {reason}")
    print("Move real credentials into your local .env file and keep placeholders in tracked files.")
    return 1


if __name__ == "__main__":
    sys.exit(main())