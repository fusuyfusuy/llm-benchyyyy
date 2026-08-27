with open("bench/harness/cli_adapter.py", "r") as f:
    text = f.read()

auth_check = """
    # Pre-flight check for authentication or rate limit masking in stderr/stdout
    combined_output = proc.stdout + " " + proc.stderr
    lower_out = combined_output.lower()
    if "401 unauthorized" in lower_out or "429 too many requests" in lower_out or "rate limit" in lower_out or "authentication error" in lower_out or "api key not valid" in lower_out:
        raise RuntimeError(f"FATAL: Auth/RateLimit error detected masking as task failure! Aborting. Output: {combined_output[-500:]}")
"""

text = text.replace('def _extract_fields(config: HarnessConfig, proc: subprocess.CompletedProcess) -> tuple[str, int | None, int | None, float | None, int | None]:\n    """Parse', 'def _extract_fields(config: HarnessConfig, proc: subprocess.CompletedProcess) -> tuple[str, int | None, int | None, float | None, int | None]:\n' + auth_check + '\n    """Parse')

with open("bench/harness/cli_adapter.py", "w") as f:
    f.write(text)
