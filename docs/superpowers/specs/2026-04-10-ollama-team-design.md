# Ollama Team — Self-Improving Agent System

## Context

Build a fully autonomous, self-improving AI agent team running on local Ollama models (CPU-only). The agents' sole purpose is to improve their own codebase — writing code, reviewing each other, testing, and deploying changes without human intervention. Dylan monitors via a web dashboard and provides thumbs up/down feedback that drives the improvement loop. The end goal is zero dependency on Claude or any external AI service.

**Hardware**: IRONPC2 — Intel Core Ultra 5 235 (14 cores), 32GB RAM, no GPU.

## Architecture: Git-Centric Pipeline

Git is the coordination backbone. Every improvement goes through a branch → code → review → test → merge → deploy pipeline. The orchestrator manages the pipeline; agents do the work.

**Why git-centric**: Free version history, trivial rollback, clear audit trail. When agents break themselves (and they will), `git revert` fixes it.

## Tech Stack

| Layer | Technology |
|-------|------------|
| LLM Runtime | Ollama (CPU-only, Q4_K_M quantized models) |
| Backend | Python 3.12+, FastAPI, SQLite |
| Frontend | React (Vite), TailwindCSS |
| Task Queue | In-process asyncio (no external broker needed) |
| Version Control | Git (local repo, the project itself) |
| Process Management | Supervisor or systemd for auto-restart |

## Agent Roles

| Agent | Purpose | Model | Notes |
|-------|---------|-------|-------|
| **Planner** | Evaluates system, identifies weaknesses, prioritizes improvements | `qwen2.5:7b` | Strongest reasoning needed |
| **Coder** | Implements changes on feature branches | `qwen2.5-coder:7b` | Code-specialized model |
| **Reviewer** | Reviews diffs, approves/rejects changes | `qwen2.5-coder:7b` | Reads and critiques code |
| **Tester** | Writes and runs tests, validates changes | `qwen2.5-coder:3b` | Smaller model, faster turnaround |
| **Deployer** | Git merges, service restarts, health checks, rollbacks | Scripted (minimal LLM) | Mostly deterministic shell operations |

**Memory management**: Only one 7B model loaded at a time (~5-6GB Q4_K_M). Agents take turns. Orchestrator swaps models between pipeline stages.

## Self-Improvement Loop

The core cycle runs continuously with a configurable cooldown (default: 2 minutes between cycles):

### Step 1: EVALUATE (Planner)
- Analyze recent feedback (thumbs down = problems, thumbs up = good direction)
- Review test results and error logs
- Identify slowest/weakest components
- Check for missing capabilities

### Step 2: PROPOSE (Planner)
- Create a structured improvement proposal:
  - Description of change
  - Files to modify
  - Expected outcome
  - Risk level (low/medium/high)

### Step 3: BRANCH (Deployer)
- Create a git branch: `improve/<short-description>-<timestamp>`

### Step 4: CODE (Coder)
- Read relevant files from the codebase
- Implement the proposed change on the branch
- Max 3 retry attempts if the change doesn't compile/parse

### Step 5: REVIEW (Reviewer)
- Read the diff
- Check for bugs, logic errors, style issues
- Approve or reject with explanation
- Rejected → back to step 4 (retry) or abandon after 3 attempts

### Step 6: TEST (Tester)
- Run existing test suite
- Write new tests for the change if applicable
- All tests must pass
- Failed → back to step 4 or abandon

### Step 7: MERGE (Deployer)
- Merge branch into main
- Restart affected services

### Step 8: VERIFY (Deployer)
- Hit health endpoint within 60 seconds
- If unhealthy → auto-rollback (`git revert` + restart)

### Step 9: RECORD
- Log full cycle details to SQLite
- Show on dashboard as a new card awaiting feedback
- Feed Dylan's eventual thumbs up/down into the next EVALUATE cycle

## Feedback System

### Storage (SQLite)

```sql
CREATE TABLE cycles (
    id TEXT PRIMARY KEY,           -- UUID
    started_at DATETIME,
    completed_at DATETIME,
    status TEXT CHECK(status IN ('running', 'success', 'failed', 'rolled_back', 'abandoned')),
    proposal TEXT,                  -- JSON: description, files, expected outcome, risk
    branch_name TEXT,
    diff TEXT,                      -- Full diff of changes
    test_output TEXT,
    deploy_log TEXT,
    rollback_reason TEXT            -- NULL if no rollback
);

CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    cycle_id TEXT NOT NULL REFERENCES cycles(id),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    rating TEXT CHECK(rating IN ('up', 'down')),
    change_summary TEXT,
    files_changed TEXT,             -- JSON array
    agent_prompts_version TEXT,     -- JSON map of agent->prompt hash
    note TEXT                       -- optional free-text from Dylan
);
```

### Phase 1: Prompt Evolution
- Each agent has a versioned system prompt in `prompts/<agent>.md`
- After accumulating feedback, Planner reviews patterns:
  - Thumbs-down patterns → "stop doing X" rules added to prompts
  - Thumbs-up patterns → "keep doing Y" rules reinforced
- Prompt modifications go through the same improvement pipeline
- Old versions preserved in git history

### Phase 2: Fine-Tuning (Future)
- Thumbs-up cycles → positive training examples
- Thumbs-down cycles → negative examples
- When 50+ examples accumulate → trigger fine-tuning (LoRA via unsloth or Ollama Modelfile)
- Fine-tuned models replace base models in agent configs

## Dashboard UI (React)

### 1. Live Activity Feed (Home)
- Real-time: which agent is active, what pipeline step
- Current model loaded
- CPU/RAM usage
- Streaming log output

### 2. Cycle History
- All completed improvement cycles
- Summary, status (success/failed/rolled-back), duration
- Expand: proposal, diff, test results, deploy log
- Inline thumbs up/down buttons
- Optional note field
- Filters: agent, status, date, rating

### 3. Agent Profiles
- Per-agent: current prompt, model, success rate
- Prompt version history with diff view
- Stats: avg cycle time, success rate, feedback score

### 4. System Health
- Ollama status, loaded model
- CPU/RAM/disk usage
- Service uptime
- Git status (branch, recent commits)
- Rollback history

### 5. Settings
- Cycle speed / cooldown
- Pause/resume loop
- Model selection per agent
- Risk tolerance

## Safety & Guardrails

### Protected (agents CANNOT modify)
- Rollback and health check system
- SQLite database / feedback data
- Dashboard frontend code
- Git configuration
- Ollama configuration
- System-level files

### Enforcement
- Hardcoded exclusion list in orchestrator — file paths agents cannot touch
- Changes tested in subprocess before merge
- Health check after every deploy; failure → auto-rollback within 60s
- Process timeout: 5 minutes per agent invocation (configurable)
- Rate limiting: minimum 2-minute cooldown between cycles
- Kill switch: dashboard "STOP" button halts all activity immediately
- Max 3 retries per pipeline step before abandoning

### Failure Recovery
- Bad code → tests catch it → cycle abandoned
- Server broken after deploy → health check → auto-rollback
- Infinite loop → process timeout kills it
- Persistent garbage → thumbs-down accumulates → Planner shifts strategy

## Project Structure

```
ollama-team/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── orchestrator.py      # Pipeline controller
│   ├── agents/
│   │   ├── base.py          # Base agent class (Ollama API calls)
│   │   ├── planner.py
│   │   ├── coder.py
│   │   ├── reviewer.py
│   │   ├── tester.py
│   │   └── deployer.py
│   ├── models/
│   │   ├── cycle.py         # Improvement cycle data model
│   │   └── feedback.py      # Feedback data model
│   ├── services/
│   │   ├── git_service.py   # Git operations
│   │   ├── ollama_service.py# Ollama API wrapper + model swapping
│   │   ├── health.py        # Health checks
│   │   └── feedback.py      # Feedback CRUD
│   └── db.py                # SQLite setup
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── ActivityFeed.tsx
│   │   │   ├── CycleHistory.tsx
│   │   │   ├── AgentProfiles.tsx
│   │   │   ├── SystemHealth.tsx
│   │   │   └── Settings.tsx
│   │   └── components/
│   │       ├── CycleCard.tsx
│   │       ├── FeedbackButtons.tsx
│   │       ├── AgentStatus.tsx
│   │       ├── LogStream.tsx
│   │       └── DiffViewer.tsx
│   └── package.json
├── prompts/
│   ├── planner.md
│   ├── coder.md
│   ├── reviewer.md
│   ├── tester.md
│   └── deployer.md
├── tests/
│   ├── test_orchestrator.py
│   ├── test_agents.py
│   └── test_safety.py
├── docs/
│   └── superpowers/specs/
├── requirements.txt
└── README.md
```

## Verification Plan

1. **Ollama connectivity**: Start Ollama, pull qwen2.5-coder:7b, verify API responds
2. **Single agent**: Run Coder agent against a trivial task, confirm it generates code
3. **Pipeline**: Run one full improvement cycle end-to-end, verify branch → code → review → test → merge
4. **Rollback**: Intentionally deploy a breaking change, verify auto-rollback triggers
5. **Dashboard**: Open React app, confirm live activity streams, submit thumbs up/down, verify it persists to SQLite
6. **Feedback loop**: After N cycles with feedback, verify Planner references feedback in proposals
