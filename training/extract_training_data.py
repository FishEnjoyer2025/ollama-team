"""
Extract fine-tuning training data from Dylan's codebases.

Generates instruction/response pairs from:
1. Git history (commit message = instruction, diff = response)
2. Code files (file path + content = examples of how Dylan writes code)
3. CLAUDE.md files (explicit rules and conventions)
4. Project structure patterns

Output: JSONL file for fine-tuning with unsloth/LoRA
"""
import json
import subprocess
import os
from pathlib import Path
from typing import Generator

REPOS = [
    "FishEnjoyer2025/cabman",
    "FishEnjoyer2025/quanttrader",
    "FishEnjoyer2025/oracle",
    "FishEnjoyer2025/kc-powerwash",
    "FishEnjoyer2025/callpilot",
    "FishEnjoyer2025/mac-estimator",
    "FishEnjoyer2025/mac-design",
    "FishEnjoyer2025/ollama-team",
    "FishEnjoyer2025/bet-bot",
]

REPOS_DIR = Path("/root/training-repos")
OUTPUT_DIR = Path("/root/ollama-team/training/data")


def clone_repos():
    """Clone all repos."""
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    for repo in REPOS:
        name = repo.split("/")[1]
        dest = REPOS_DIR / name
        if dest.exists():
            print(f"  {name}: already cloned")
            continue
        print(f"  Cloning {repo}...")
        subprocess.run(
            ["gh", "repo", "clone", repo, str(dest)],
            capture_output=True,
        )


def extract_git_history(repo_path: Path, max_commits: int = 200) -> Generator[dict, None, None]:
    """Extract commit message + diff pairs as training examples."""
    result = subprocess.run(
        ["git", "log", f"--max-count={max_commits}", "--format=%H|||%s|||%an", "--no-merges"],
        cwd=repo_path, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return

    for line in result.stdout.strip().split("\n"):
        if not line or "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) != 3:
            continue
        sha, message, author = parts

        # Get the diff for this commit
        diff_result = subprocess.run(
            ["git", "diff", f"{sha}~1", sha, "--stat", "--unified=3"],
            cwd=repo_path, capture_output=True, text=True,
        )
        diff = diff_result.stdout[:3000] if diff_result.returncode == 0 else ""
        if not diff or len(diff) < 20:
            continue

        # Skip automated/bot commits
        if "Co-Authored-By: Claude" in message or "bot" in author.lower():
            continue

        repo_name = repo_path.name
        yield {
            "instruction": f"In the {repo_name} project, make this change: {message}",
            "input": f"Repository: {repo_name}\nRecent diff context:\n{diff[:1500]}",
            "output": diff[:2000],
            "source": "git_history",
            "repo": repo_name,
        }


def extract_code_examples(repo_path: Path) -> Generator[dict, None, None]:
    """Extract code files as examples of Dylan's coding style."""
    extensions = {".py", ".cs", ".tsx", ".ts", ".js"}
    skip_dirs = {"node_modules", ".git", "venv", "__pycache__", "dist", "bin", "obj"}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            path = Path(root) / f
            if path.suffix not in extensions:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if len(content) < 50 or len(content) > 10000:
                continue

            rel_path = path.relative_to(repo_path)
            repo_name = repo_path.name
            lang = {".py": "Python", ".cs": "C#", ".tsx": "TypeScript/React", ".ts": "TypeScript", ".js": "JavaScript"}.get(path.suffix, "code")

            yield {
                "instruction": f"Write the {lang} file {rel_path} for the {repo_name} project.",
                "input": f"Repository: {repo_name}\nFile: {rel_path}\nLanguage: {lang}",
                "output": content[:4000],
                "source": "code_file",
                "repo": repo_name,
            }


def extract_claude_md(repo_path: Path) -> Generator[dict, None, None]:
    """Extract CLAUDE.md rules as training data for conventions."""
    for claude_md in repo_path.rglob("CLAUDE.md"):
        try:
            content = claude_md.read_text(encoding="utf-8")
        except Exception:
            continue
        if len(content) < 20:
            continue

        repo_name = repo_path.name
        yield {
            "instruction": f"What are the coding rules and conventions for the {repo_name} project?",
            "input": f"Repository: {repo_name}",
            "output": content[:4000],
            "source": "claude_md",
            "repo": repo_name,
        }


def extract_project_structure(repo_path: Path) -> Generator[dict, None, None]:
    """Extract project structure as context."""
    skip_dirs = {"node_modules", ".git", "venv", "__pycache__", "dist", "bin", "obj", ".vs"}
    structure = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted([d for d in dirs if d not in skip_dirs])
        level = len(Path(root).relative_to(repo_path).parts)
        if level > 3:
            dirs.clear()
            continue
        indent = "  " * level
        folder = Path(root).name
        structure.append(f"{indent}{folder}/")
        for f in sorted(files)[:20]:
            structure.append(f"{indent}  {f}")

    if len(structure) < 3:
        return

    repo_name = repo_path.name
    yield {
        "instruction": f"What is the project structure of {repo_name}?",
        "input": f"Repository: {repo_name}",
        "output": "\n".join(structure[:200]),
        "source": "structure",
        "repo": repo_name,
    }


def build_system_prompt_examples() -> list[dict]:
    """Create examples that teach the model Dylan's preferences."""
    return [
        {
            "instruction": "How should you communicate with Dylan?",
            "input": "",
            "output": "Terse responses. No trailing summaries. No emojis. Lead with action or answer. Don't ask clarifying questions unless truly blocked. Implement full plans in one shot.",
            "source": "preferences",
            "repo": "meta",
        },
        {
            "instruction": "What are Dylan's projects?",
            "input": "",
            "output": "CabMan (WPF/.NET 8 cabinet design), QuantTrader (Python quant trading), Kalshi Bot (prediction markets), Sports Betting (BetAnalyzer), KC PowerWash (service business platform), CallPilot (voice AI), MAC Estimator (WPF bidding tool), Ollama Team (self-improving AI agents).",
            "source": "preferences",
            "repo": "meta",
        },
        {
            "instruction": "What rules apply to CabMan?",
            "input": "",
            "output": "Use BLC for blind corner cabinets, NEVER BBC. Drawer stacks: top drawer height matches standard base, rest equal. Editing: in-viewport inline, not separate dialog popups. StandardCabinetCalculator.cs is the single source of truth for parts.",
            "source": "preferences",
            "repo": "meta",
        },
        {
            "instruction": "What should you verify before saying done?",
            "input": "",
            "output": "Never declare done without end-to-end verification. Run it, watch the first cycle, confirm it DOES the thing. If you can't verify: explicitly say 'I CANNOT VERIFY: [what]' and list what needs manual checking.",
            "source": "preferences",
            "repo": "meta",
        },
    ]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "training_data.jsonl"

    print("=== Training Data Extraction ===")
    print()

    # Clone repos
    print("[1] Cloning repositories...")
    clone_repos()
    print()

    # Extract everything
    all_examples = []

    print("[2] Extracting git history...")
    for repo_dir in REPOS_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        count = 0
        for example in extract_git_history(repo_dir):
            all_examples.append(example)
            count += 1
        print(f"  {repo_dir.name}: {count} commit examples")

    print("[3] Extracting code files...")
    for repo_dir in REPOS_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        count = 0
        for example in extract_code_examples(repo_dir):
            all_examples.append(example)
            count += 1
        print(f"  {repo_dir.name}: {count} code examples")

    print("[4] Extracting CLAUDE.md rules...")
    for repo_dir in REPOS_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        for example in extract_claude_md(repo_dir):
            all_examples.append(example)
            print(f"  {repo_dir.name}: found CLAUDE.md")

    print("[5] Extracting project structures...")
    for repo_dir in REPOS_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        for example in extract_project_structure(repo_dir):
            all_examples.append(example)

    print("[6] Adding preference examples...")
    all_examples.extend(build_system_prompt_examples())

    # Write output
    with open(output_file, "w", encoding="utf-8") as f:
        for example in all_examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print()
    print(f"=== Done: {len(all_examples)} training examples ===")
    print(f"Output: {output_file}")

    # Stats
    by_source = {}
    by_repo = {}
    for ex in all_examples:
        src = ex.get("source", "unknown")
        repo = ex.get("repo", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
        by_repo[repo] = by_repo.get(repo, 0) + 1

    print("\nBy source:")
    for k, v in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("\nBy repo:")
    for k, v in sorted(by_repo.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
