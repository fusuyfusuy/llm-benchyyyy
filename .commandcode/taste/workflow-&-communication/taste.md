# Workflow & Communication
- Prefers a plan-first workflow: asks for a written plan before implementation, including for refactors and new systems ("plan.", "plan now", "plan and audit first", "make the output engine coherent for all checkers. plan."). Confidence: 0.9
- Delegates verification and auditing to subagents rather than doing it inline ("verify and audit using subagent"). Confidence: 0.85
- Wants landscape research before designing new tools/benchmarks (commissioned research on benchmark/eval methodologies before designing a benchmark system). Confidence: 0.8
- Wants finished work shipped as a proper GitHub repo with README and guides via gh ("merge and create a repo using gh and push there with readme and guides and everything"). Confidence: 0.9
- Picks up context from Claude session summaries between sessions ("check latest claude session summaries here"). Confidence: 0.6
- When adding/integrating something new, asks the agent to first find out how existing sibling tools handle it ("add ccheck to the path, find out how it is done for bcheck and ocheck") — investigate the established pattern in the repo before acting, rather than inventing a new mechanism. Confidence: 0.7
- Communicates in terse, directive one-liners (repeatedly just says "continue" to resume long builds rather than re-explaining scope; asks abbreviated status questions like "what work is done to do?"). Confidence: 0.75
- When planning, wants to be "grilled" — asked pointed clarifying questions on the design forks that shape the implementation before a plan is finalized ("plan first, grill"). Confidence: 0.9
- When grilled with option-style questions, goes with the options marked "Recommended" — so flag a clear recommendation when asking design-fork questions (approved the resulting all-recommendations plan unchanged). Confidence: 0.6
