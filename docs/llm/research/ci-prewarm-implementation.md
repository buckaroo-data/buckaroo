# CI Pre-Warming: Implementation Plans

**Baseline:** 49s total. Critical path: warmup (11s) -> pw-jupyter (37s).

Each technique has a standalone implementation plan with files to change, code sketches,
validation steps, and risks.

## Implementation Order

| Priority | Plan | Savings | Effort |
|----------|------|---------|--------|
| 1 | [Tech 1+5a: Server pool + warm kernels](impl-tech1-5a-server-pool.md) | 8-11s | 1-2 days |
| 2 | [Tech 2: Chromium pre-start](impl-tech2-chromium-prestart.md) | 2-3s | 0.5 day |
| 3 | [Tech 7: Transcript oracle + Layer B](impl-tech7-transcript-oracle.md) | 0-37s (cache hit) | 2-3 days |
| 4 | [Tech 5a: Keep kernels alive (cold start)](impl-tech5a-keep-kernels-alive.md) | 4-6s | 0.5 day |
| 5 | [Tech 5c: cpuset isolation](impl-tech5c-cpuset-isolation.md) | 3-6s (unmeasured) | 0.5 day |
| 6 | [Tech 6: Webhook pre-build](impl-tech6-webhook-prebuild.md) | 2-3s | 0.5 day |

**Skip:** Tech 3 (Node pre-start), Tech 4 (.pyc cache), Tech 5b (reschedule jobs),
Tech 5d (pytest pre-fork). See [research doc](ci-prewarm-research.md) for rationale.

## First question to resolve

Before implementing Tech 1, verify the critical path from CI logs. If the build path
(16s) finishes after warmup (11s), warmup is not the true bottleneck and Tech 1 savings
drop to ~5s.
