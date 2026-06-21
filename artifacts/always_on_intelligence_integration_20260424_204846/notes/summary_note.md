# Always-On Intelligence Integration Summary

Focused tests:
- 63 passed

Listen-only verification:
- execution_mode=LISTEN_ONLY
- runtime_mode=listen_only
- AP Top News runtime ingestion completed and surfaced as FRESH
- whale scoring surfaced as STALE from persisted whale data
- AI digest remained ABSENT because ANTHROPIC_API_KEY was not configured
- paper_orders stayed at 3 and paper_positions stayed at 3 during the listen-only proof window, so no trading occurred

Paper verification:
- execution_mode=PAPER
- runtime_mode=paper_safe
- awareness layer remained active with AP Top News still FRESH
- clean paper reset succeeded before the run
- short clean paper run produced 40 paper signals, 3 filled paper orders, and 3 open paper positions
- paper capital state updated to available_cash_usd=73.7502 and deployed_notional_usd=26.24981

Tier-1 news source truth:
- AP integrated operationally through official site parsing
- Reuters registered but disabled due access/auth block on public endpoint
- Bloomberg registered but disabled due access block on public endpoint
- FT registered but disabled due security block on public endpoint

Whale truth:
- Whale scoring is now visible in the canonical runtime surfaces
- Current runtime path refreshes whale scoring over persisted whale data
- True continuous whale event ingestion remains partial
