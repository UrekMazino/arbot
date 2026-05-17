Before making changes:
1. Read docs/ai/OKXSTATBOT_PROJECT_CONTEXT.md.
2. Read docs/ai/OKXSTATBOT_CURRENT_STATE.md.
3. Read docs/ai/OKXSTATBOT_ROADMAP.md.
4. Read docs/ai/OKXSTATBOT_DECISION_LOG.md.
5. Confirm whether the requested task is:
   - read-only audit
   - config-only change
   - diagnostics-only change
   - behavior change
   - trading/execution change

Default safety rules:
- Do not modify order execution unless explicitly requested.
- Do not change live trading behavior during audits.
- Do not scale notional.
- Do not enable Advanced ML live.
- Do not activate routers.
- Prefer one variable change per controlled run.
- Always report files changed, behavior changed, tests run, and what was intentionally not changed.
