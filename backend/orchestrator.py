import asyncio
import json
import logging
import uuid
from enum import Enum
from typing import Optional

from backend import db
from backend.agents.planner import planner
from backend.agents.coder import coder
from backend.agents.reviewer import reviewer
from backend.agents.tester import tester
from backend.services.tools import validate_edits, validate_python_syntax
from backend.agents.deployer import deployer
from backend.services import git_service

logger = logging.getLogger(__name__)

# Only protect what would brick the system if broken
PROTECTED_PATHS = {
    "backend/orchestrator.py",
    "backend/main.py",
    "backend/db.py",
    ".gitignore",
    ".git",
    "ollama_team.db",
}

# Core frontend files protected, but agents can modify pages/components
PROTECTED_PREFIXES = (".git/", "docs/")
PROTECTED_FRONTEND = {
    "frontend/src/main.tsx",
    "frontend/src/App.tsx",
    "frontend/src/api.ts",
    "frontend/src/hooks/useWebSocket.ts",
    "frontend/package.json",
    "frontend/vite.config.ts",
    "frontend/index.html",
}


class CycleStep(str, Enum):
    EVALUATE = "evaluate"
    PROPOSE = "propose"
    BRANCH = "branch"
    CODE = "code"
    REVIEW = "review"
    TEST = "test"
    MERGE = "merge"
    VERIFY = "verify"
    RECORD = "record"


class Orchestrator:
    def __init__(self, broadcast=None):
        self._running = False
        self._paused = False
        self._stopped = False
        self._current_step: Optional[CycleStep] = None
        self._current_cycle_id: Optional[str] = None
        self._broadcast = broadcast  # WebSocket broadcast function

    async def _emit(self, event_type: str, data: dict):
        """Send a real-time event to the dashboard."""
        if self._broadcast:
            await self._broadcast({
                "type": event_type,
                "cycle_id": self._current_cycle_id,
                "step": self._current_step.value if self._current_step else None,
                **data,
            })

    def _validate_file_paths(self, paths: list[str]) -> list[str]:
        """Filter out protected file paths. Returns only allowed paths."""
        allowed = []
        for p in paths:
            if p in PROTECTED_PATHS or p in PROTECTED_FRONTEND:
                logger.warning(f"Blocked edit to protected file: {p}")
                continue
            if any(p.startswith(prefix) for prefix in PROTECTED_PREFIXES):
                logger.warning(f"Blocked edit to protected path: {p}")
                continue
            allowed.append(p)
        return allowed

    async def run_loop(self):
        """Main improvement loop. Runs continuously until stopped."""
        self._running = True
        self._stopped = False
        logger.info("Orchestrator started")
        await self._emit("system", {"action": "started"})

        while self._running and not self._stopped:
            # Check settings
            settings = await db.get_settings()
            if settings.get("stopped") == "true":
                self._stopped = True
                break
            if settings.get("paused") == "true":
                await asyncio.sleep(5)
                continue

            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Cycle failed with unexpected error: {e}", exc_info=True)
                await self._emit("error", {"message": str(e)})

            # Cooldown between cycles
            cooldown = int(settings.get("cycle_cooldown_seconds", "120"))
            logger.info(f"Cooling down for {cooldown}s before next cycle")
            await self._emit("system", {"action": "cooldown", "seconds": cooldown})
            await asyncio.sleep(cooldown)

        logger.info("Orchestrator stopped")
        await self._emit("system", {"action": "stopped"})

    async def run_cycle(self) -> Optional[str]:
        """Run one complete improvement cycle. Returns cycle_id or None."""
        cycle_id = str(uuid.uuid4())[:8]
        self._current_cycle_id = cycle_id
        settings = await db.get_settings()
        max_retries = int(settings.get("max_retries_per_step", "3"))

        logger.info(f"=== Starting cycle {cycle_id} ===")
        await self._emit("cycle", {"action": "started"})

        # Ensure we're on main
        await git_service.checkout("main")
        branch_name = None

        try:
            # --- Step 1 & 2: EVALUATE + PROPOSE (Planner) ---
            self._current_step = CycleStep.EVALUATE
            await self._emit("step", {"action": "started", "agent": "planner"})
            logger.info(f"[{cycle_id}] Planner evaluating...")

            proposal = await planner.evaluate_and_propose()
            logger.info(f"[{cycle_id}] Proposal: {proposal.get('description', 'unknown')}")
            await self._emit("step", {"action": "completed", "agent": "planner", "proposal": proposal})

            # Validate proposed files aren't protected
            if proposal.get("files"):
                proposal["files"] = self._validate_file_paths(proposal["files"])
                if not proposal["files"]:
                    logger.warning(f"[{cycle_id}] All proposed files are protected, abandoning")
                    await db.create_cycle(cycle_id, proposal)
                    await db.complete_cycle(cycle_id, "abandoned", rollback_reason="All target files are protected")
                    return cycle_id

            # Create cycle record
            await db.create_cycle(cycle_id, proposal)

            # --- Step 3: BRANCH (Deployer) ---
            self._current_step = CycleStep.BRANCH
            await self._emit("step", {"action": "started", "agent": "deployer"})
            branch_name = await deployer.create_branch(proposal.get("description", "improvement"))
            await db.update_cycle(cycle_id, branch_name=branch_name)
            await self._emit("step", {"action": "completed", "agent": "deployer", "branch": branch_name})

            # Determine if this is a "safe" change (prompts/tests only — skip review)
            safe_change = all(
                f.startswith("prompts/") or f.startswith("tests/")
                for f in proposal.get("files", [])
            )

            # --- Step 4: CODE (Coder) with retries + error feedback ---
            edits = []
            last_error = ""
            for attempt in range(max_retries):
                self._current_step = CycleStep.CODE
                await self._emit("step", {"action": "started", "agent": "coder", "attempt": attempt + 1})
                logger.info(f"[{cycle_id}] Coder implementing (attempt {attempt + 1})...")

                # Feed previous error back to coder on retry
                if last_error:
                    proposal["_retry_error"] = last_error

                edits = await coder.implement(proposal)

                if not edits:
                    last_error = "No edits produced. Output valid JSON: [{\"path\": \"...\", \"content\": \"...\"}]"
                    logger.warning(f"[{cycle_id}] Coder produced no edits")
                    if attempt < max_retries - 1:
                        continue
                    await self._abandon(cycle_id, branch_name, "Coder produced no edits after retries")
                    return cycle_id

                # Filter protected files
                edits = [e for e in edits if e.get("path") not in PROTECTED_PATHS
                         and not any(e.get("path", "").startswith(p) for p in PROTECTED_PREFIXES)]

                if not edits:
                    await self._abandon(cycle_id, branch_name, "All edits targeted protected files")
                    return cycle_id

                # Apply edits
                modified = await coder.apply_edits(edits, allowed_paths=proposal.get("files", []))

                if not modified:
                    last_error = "Edits were blocked — use exact file paths from the proposal"
                    if attempt < max_retries - 1:
                        continue
                    await self._abandon(cycle_id, branch_name, "No files written after filtering")
                    return cycle_id

                # Validate syntax
                valid, syntax_issues = await validate_edits(edits)
                if not valid:
                    last_error = f"Fix these syntax errors: {'; '.join(syntax_issues)}"
                    logger.warning(f"[{cycle_id}] Syntax validation failed: {syntax_issues}")
                    await self._emit("step", {"action": "validation_failed", "issues": syntax_issues})
                    if attempt < max_retries - 1:
                        continue
                    await self._abandon(cycle_id, branch_name, f"Syntax errors: {'; '.join(syntax_issues)}")
                    return cycle_id

                await self._emit("step", {"action": "completed", "agent": "coder", "files": modified})

                # Commit on the branch
                await deployer.commit_changes(
                    f"[{cycle_id}] {proposal.get('description', 'improvement')[:60]}",
                    modified,
                )

                # --- Step 5: REVIEW (skip for safe changes) ---
                if safe_change:
                    logger.info(f"[{cycle_id}] Skipping review (safe change: prompts/tests only)")
                    await self._emit("step", {"action": "skipped", "agent": "reviewer", "reason": "safe change"})
                    break

                self._current_step = CycleStep.REVIEW
                await self._emit("step", {"action": "started", "agent": "reviewer"})
                logger.info(f"[{cycle_id}] Reviewer checking...")

                review = await reviewer.review(proposal, branch_name)
                await self._emit("step", {"action": "completed", "agent": "reviewer", "review": review})

                if review["approved"]:
                    logger.info(f"[{cycle_id}] Review approved: {review['explanation']}")
                    break
                else:
                    last_error = f"Reviewer rejected: {review['explanation']}. Issues: {review.get('issues', [])}"
                    logger.warning(f"[{cycle_id}] Review rejected: {review['explanation']}")
                    if attempt < max_retries - 1:
                        continue
                    await self._abandon(cycle_id, branch_name, f"Review rejected: {review['explanation']}")
                    return cycle_id

            # --- Step 6: TEST (run tests + retry with error if failed) ---
            self._current_step = CycleStep.TEST
            await self._emit("step", {"action": "started", "agent": "tester"})
            logger.info(f"[{cycle_id}] Tester validating...")

            test_result = await tester.validate(proposal, edits)
            await db.update_cycle(cycle_id, test_output=test_result["output"][:5000])
            await self._emit("step", {"action": "completed", "agent": "tester", "passed": test_result["passed"]})

            if not test_result["passed"]:
                # Try one more time — feed the error to the coder
                test_error = test_result["output"][-1000:]
                logger.warning(f"[{cycle_id}] Tests failed, attempting fix...")
                proposal["_retry_error"] = f"Tests failed with this output:\n{test_error}\nFix the code."

                self._current_step = CycleStep.CODE
                edits = await coder.implement(proposal)
                if edits:
                    edits = [e for e in edits if e.get("path") not in PROTECTED_PATHS
                             and not any(e.get("path", "").startswith(p) for p in PROTECTED_PREFIXES)]
                    modified = await coder.apply_edits(edits, allowed_paths=proposal.get("files", []))
                    if modified:
                        valid, _ = await validate_edits(edits)
                        if valid:
                            await deployer.commit_changes(f"[{cycle_id}] Fix: {proposal.get('description', '')[:50]}", modified)
                            test_result = await tester.validate(proposal, edits)
                            await db.update_cycle(cycle_id, test_output=test_result["output"][:5000])

                if not test_result["passed"]:
                    await self._abandon(cycle_id, branch_name, f"Tests failed: {test_result['summary']}")
                    return cycle_id

            # --- Step 7: MERGE (Deployer) ---
            self._current_step = CycleStep.MERGE
            await self._emit("step", {"action": "started", "agent": "deployer"})
            logger.info(f"[{cycle_id}] Merging to main...")

            diff = await git_service.get_diff(branch_name)
            merged = await deployer.merge_to_main(branch_name)

            if not merged:
                await self._abandon(cycle_id, branch_name, "Merge failed")
                return cycle_id

            await db.update_cycle(cycle_id, diff=diff[:10000])
            await self._emit("step", {"action": "completed", "agent": "deployer"})

            # --- Step 8: VERIFY (Health check) ---
            self._current_step = CycleStep.VERIFY
            await self._emit("step", {"action": "started", "agent": "deployer"})
            logger.info(f"[{cycle_id}] Verifying health...")

            healthy = await deployer.verify_health()

            if not healthy:
                logger.error(f"[{cycle_id}] Health check failed, rolling back!")
                await deployer.rollback(f"Health check failed after cycle {cycle_id}")
                await db.complete_cycle(
                    cycle_id, "rolled_back",
                    rollback_reason="Health check failed after deploy",
                    deploy_log="Auto-rollback triggered",
                )
                await self._emit("step", {"action": "rolled_back"})
                return cycle_id

            # --- Step 9: RECORD ---
            self._current_step = CycleStep.RECORD
            await db.complete_cycle(cycle_id, "success", deploy_log="Deployed successfully")
            logger.info(f"=== Cycle {cycle_id} completed successfully ===")
            await self._emit("cycle", {"action": "completed", "status": "success"})
            return cycle_id

        except Exception as e:
            logger.error(f"[{cycle_id}] Cycle failed: {e}", exc_info=True)
            if branch_name:
                await self._cleanup_branch(branch_name)
            await db.complete_cycle(cycle_id, "failed", rollback_reason=str(e))
            await self._emit("cycle", {"action": "failed", "error": str(e)})
            return cycle_id

    async def _abandon(self, cycle_id: str, branch_name: Optional[str], reason: str):
        """Abandon a cycle and clean up."""
        logger.warning(f"[{cycle_id}] Abandoning: {reason}")
        if branch_name:
            await self._cleanup_branch(branch_name)
        await db.complete_cycle(cycle_id, "abandoned", rollback_reason=reason)
        await self._emit("cycle", {"action": "abandoned", "reason": reason})

    async def _cleanup_branch(self, branch_name: str):
        """Switch back to main and delete the feature branch."""
        await git_service.checkout("main")
        await git_service.delete_branch(branch_name)

    def stop(self):
        """Signal the loop to stop."""
        self._running = False
        self._stopped = True

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    @property
    def status(self) -> dict:
        return {
            "running": self._running,
            "paused": self._paused,
            "stopped": self._stopped,
            "current_step": self._current_step.value if self._current_step else None,
            "current_cycle_id": self._current_cycle_id,
        }
