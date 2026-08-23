# LLM Benchmark Suite: Tutorial & How-To

This guide explains how to use the `llm-benchyyyy` runner to execute benchmarking tasks across four supported coding harnesses: **Antigravity (`agy`)**, **Pi-Agent (`pi`)**, **OpenCode (`opencode`)**, and **Claude Code (`claude-code`)**.

## 1. Environment Setup

### Install the benchmark runner
You need to install the `bench` package locally so Python can resolve the module:
```bash
# From the repository root
pip install -e .
```

### Build the Sandbox Image
The benchmark runs tasks inside an ephemeral Docker container to prevent destructive commands from harming your host. You must build the base image once:
```bash
docker build -f docker/harness-base.Dockerfile -t llm-bench-harness .
```
*(This image comes pre-installed with all 4 CLI tools).*

## 2. Authentication & Credentials

Rather than forcing you to paste API keys or re-authenticate inside Docker, the runner bind-mounts your **host machine's existing CLI configuration directories** into the sandbox. 

You must be logged into the respective CLI tools on your host machine before running the benchmark:

- **Claude Code**: Reads `~/.claude` or `~/.claude.json`. (Run `claude login` on host).
- **Antigravity (`agy`)**: Reads/Writes `~/.gemini`. (Run `agy login` on host).
- **Pi-Agent (`pi`)**: Reads/Writes `~/.pi/agent`. (Run `pi login` on host).
- **OpenCode (`opencode`)**: Reads `~/.config/opencode`. (Run `opencode login` on host).

*Note: Both `agy` and `pi` are mounted **read-write** because they rely on locking mechanisms, caching, and state databases (e.g., SQLite brain) during execution.*

## 3. Running a Benchmark

The command to execute a benchmark is `python -m bench run`. It takes four primary arguments:
- `--task`: Path to the markdown file in `tasks/`.
- `--harness`: The CLI to use (`claude-code`, `agy`, `pi-agent`, `opencode`).
- `--model`: The underlying model flag to pass to the CLI.
- `--trials`: How many times to repeat the task (must be ≥ 3 for statistical significance).

### Example: Running a single task

Let's run the `fix-off-by-one-pagination` task against the 4 harnesses. 

**For Claude Code:**
```bash
python -m bench run --task tasks/coding/fix-off-by-one-pagination.md \
    --harness claude-code --model claude-sonnet-5 --trials 3
```

**For Antigravity:**
```bash
python -m bench run --task tasks/coding/fix-off-by-one-pagination.md \
    --harness antigravity --model gemini-2.5-pro --trials 3
```

**For Pi-Agent:**
```bash
python -m bench run --task tasks/coding/fix-off-by-one-pagination.md \
    --harness pi-agent --model gemini-2.5-flash --trials 3
```

**For OpenCode:**
```bash
python -m bench run --task tasks/coding/fix-off-by-one-pagination.md \
    --harness opencode --model opencode-go/muse-spark --trials 3
```

## 4. How Grading Works

When you run a task, the runner performs the following sequence:
1. **Setup**: Reads the `tasks/...md` file, creates a temporary workspace on the host, and dumps the seeded files into it.
2. **Execute**: Launches the `llm-bench-harness` Docker container mounted to the workspace, executing the harness command.
3. **Grade**: Reads the `expected/...md` rubric and executes the `## Check` bash script. If the script exits with `0`, the trial is marked as a **PASS**. If it exits `> 0`, it is a **FAIL**.
4. **Log**: Records the exit code, duration, token usage, and cost to `results/runs.jsonl`.

## 5. Viewing the Report

Once your runs have finished, you generate an aggregated markdown report showing Pass Rates, Costs, and Latency:
```bash
python -m bench report
```
This generates `results/report.md`. Since LLMs are non-deterministic, you will see a percentage pass rate (e.g., 66% if it passed 2 out of 3 trials).

> **WARNING**: Never commit the `results/` directory. It contains raw API trace logs and cost/token data tied to your personal API accounts.
