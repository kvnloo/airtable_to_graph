# Bend 2 × Yohei's Airtable graphs: CPU/GPU crossover investigation

**Status:** downstream CHECK experiment; neither upstream PR nor GPU speedup claim.

**Credit:** Yohei Nakajima created the original MIT-licensed `yoheinakajima/airtable_to_graph` pipeline. The adapter and tests here are additive downstream research.

## Scope and measured results

The request path is: Airtable API → linked-record discovery/edge extraction → PyVis HTML → browser graph layout. Only the middle CPU step is benchmarked. The original `find_relational_columns` prematurely broke out of a record's fields after its first linked-record column, which drops relationships. This branch fixes that correctness bug and streams eligible edges in deterministic order.

```sh
python -m unittest discover -s tests -v
python experiments/bend-crossover/benchmark.py --rows 10000 --repeats 7
python experiments/bend-crossover/benchmark.py --rows 50000 --repeats 3
```

Offline synthetic host result (2026-10-16, Python 3.13, CPU-only): 8/8 unit/integration tests pass. At 10k records/60k edges, the candidate is approximately at parity with a *correct*, not bug-compatible, reference implementation (0.95–1.01× across repeats). At 50k records/300k edges, observed speedup varied about 1.09–1.13×. This is a noisy single-host experiment; no production or full-page benefit is established.

## Bend hypothesis and architecture boundary

The candidate GPU seam is an **opt-in numeric graph snapshot kernel**, not the Python API client, secret handling, LLM calls, Flask or browser. Convert opaque Airtable record IDs to stable, bounded integer IDs in the trusted host; never send raw company/contact names or credentials to a subprocess. Preserve exact relation-edge multiset parity, including duplicate edges, against the existing Python path.

Reuse the exact **Bend 2.0.36 source-pinned compiler, proof checks, generated artifact ownership, and independent trace tests** already built in `kvnloo/hapsland/packages/agent-flow-bend`. Its generated JavaScript is useful for proof/decision interoperability but **is not CUDA acceleration**: Bend's JS target is single-threaded. Native `bend -o program` with `!` parallel calls can use supported CUDA hardware and `--gpu off` supplies a CPU comparison, but a runtime data ABI and GPU parity harness are still missing here.

There is intentionally **no runtime GPU backend in this branch**. This avoids claiming speed before measuring the transfer, process dispatch, snapshot encoding, compilation and graph-layout costs. In particular, a per-request native compile or full PyVis replacement would likely erase any microkernel gain.

## Acceptance gate before production wiring

1. Profile a representative workload to show that a numeric bulk graph operation dominates meaningful end-to-end time.
2. Freeze independent synthetic fixtures; compare exact edge/degree/query outputs for Python, Bend CPU and Bend CUDA.
3. Report warm/cold latency, kernel throughput, startup/transfer, peak memory, and whole-page elapsed time.
4. Require at least **2× isolated kernel** and **20% representative end-to-end** improvement without adding credentials exposure, incorrect graphs or different user-visible semantics. Otherwise retain the Python implementation.
5. Keep candidate upstream work off the origin until the factory HITL gate and the repository's contribution policy permit it.

Related but separate: `yoheinakajima/prezograph` is a browser-first offline deck engine—no implicit CUDA speedup from compiling its JS. `yoheinakajima/activegraph` has a recorded investment-diligence pack and **issues-first** external code contributions, so candidate backend integrations begin with a measured standalone adapter, not a drive-by runtime PR. `kvnloo/z0intelligence` can ingest shadow perf receipts without changing routing authority.
