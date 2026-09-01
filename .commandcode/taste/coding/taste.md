# Coding & Architecture

- Prefers shared/common code over duplication across sibling scripts (e.g., consolidating checker logic into a shared library like `benchmark_common.py` rather than per-script copies). Confidence: 0.8
- Prefers a coherent, unified output/rendering engine across related CLI tools (asked to make the output engine coherent for all checkers). Confidence: 0.8
- Values architectural cleanup during refactors: removing dead code, stale references, shadowed/duplicated definitions, and broken or no-op CLI flags. Confidence: 0.7
- Prefers new tools to clone the proven architecture of existing sibling tools rather than being designed from scratch (asked for an "ocheck similar" checker for command-code models). Confidence: 0.7
- Verifies derived math against known published/ground-truth values before implementing, and pins those values as test sanity assertions (e.g., computed per-request costs must reproduce docs-published figures like GLM-5.2's ≈947 req/5h). Confidence: 0.6
- Treats fabricated/default scores for missing data as a defect ("current ranking is like this and it is broken" when cheap unscored models outranked scored ones via a fake Q=78): rankings must be honest — models without benchmark coverage should get None (render "—"), sort last under benchmark orders, and never win on inflated derived metrics. Independently re-confirmed as the top P1 in a later audit round (ocheck fabricating Q=78/Pareto membership for uncovered models, verified live). Confidence: 0.7
