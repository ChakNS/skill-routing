# Evaluation Strategy

The committed evaluator is a deterministic regression suite, not evidence of universal routing accuracy.

## What is tested

`python3 scripts/evaluate_routes.py` checks the default labeled cases. The adversarial suite is run separately:

```bash
python3 scripts/evaluate_routes.py --evals evals/adversarial-routing-evals.json
```

Together these committed fixtures currently cover:

- content and coding pipelines;
- Chinese, English, and cross-language metadata;
- direct local-skill selection;
- multi-domain composition;
- abstention and router-management decisions;
- word-boundary and negation hard negatives;
- conditional candidates such as Supabase, PR creation, and deployment;
- missing-skill replacement and agent fallback persistence;
- required/forbidden stages, modules, pipelines, and selected skills.

`evals/trigger-evals.json` is a static host-activation review fixture. It documents when the main `skill-routing` skill should or should not be considered before downstream skills. It is not executed by `evaluate_routes.py` because host-level implicit activation is model/runtime behavior, not deterministic CLI behavior.

Each case declares behavioral acceptance rather than one exact internal score. A case may list multiple acceptable pipelines when more than one route is valid.

## What is not proven

A green suite proves only that the committed cases pass. It does not establish population precision, recall, calibration, output quality, or host-level implicit triggering. The matcher can still fail on unseen phrasing and specialized domains.

## Release checks

Run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/smoke_test.py
python3 scripts/evaluate_routes.py
python3 scripts/evaluate_routes.py --evals evals/adversarial-routing-evals.json
python3 skills/skill-routing/scripts/router_modules.py validate
python3 -m compileall -q scripts skills tests
bash -n scripts/install.sh
```

An empty eval file must fail. New route-pack behavior requires at least one positive case and one nearby negative or ambiguity case.

## Future statistical benchmark

Before publishing accuracy claims, create an independently labeled, semantic-cluster holdout set with at least:

- 300 prompts across supported domains;
- 30% hard negatives and ambiguous tasks;
- Chinese, English, mixed-language, terse, long, and typo slices;
- direct, pipeline, composed, clarify/abstain, and missing-capability decisions;
- inventory sizes from 10 to 1,000 skills with nearby distractors.

Report module Top-1, skill Top-1 and Top-3 recall, MRR/NDCG, abstain precision/recall, false-positive rate, worst-slice performance, latency, and confidence calibration. Compare against the host without this router, and run host-level trigger tests multiple times because model activation is nondeterministic.
