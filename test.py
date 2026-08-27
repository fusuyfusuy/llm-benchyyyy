import sys
from pathlib import Path
from bench.selfsolve import run_solution
from bench import task as task_mod, sandbox as sandbox_mod, grading
from bench.grading import spec as spec_mod

t = task_mod.parse_task(Path('tasks/agentic/ci-pipeline-recovery.md'))
spec = spec_mod.parse_grading_spec(Path('expected/agentic/ci-pipeline-recovery.md'))
sol_path = Path('solutions/agentic/ci-pipeline-recovery.sh')
script_content = sol_path.read_text()

sb = sandbox_mod.create(t.seed_files, t.setup_script)
proc = sandbox_mod.exec_in(sb, script_content)
print("EXEC STDOUT:", proc.stdout)
print("EXEC STDERR:", proc.stderr)
result = grading.executable.grade(spec, sb)
print("GRADE OUT:", result)
