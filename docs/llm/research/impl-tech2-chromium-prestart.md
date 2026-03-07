# Tech 2: Pre-Start Chromium Instances

**Goal:** Save ~2-3s of Chromium launch time from pw-jupyter. Fold into Tech 1's
post-run hook so Chromium is already running when pw-jupyter starts.

**Depends on:** Tech 1 (shares the post-run hook).

---

## What changes

### 1. New file: `ci/hetzner/browser-server.js`

```javascript
const { chromium } = require('playwright');
(async () => {
    const server = await chromium.launchServer({
        port: parseInt(process.env.PW_PORT || '3001'),
        headless: true,
        args: ['--disable-dev-shm-usage', '--no-sandbox'],
    });
    console.log(`Browser server: ${server.wsEndpoint()}`);
    // Write WS endpoint to file for Playwright config to read
    const fs = require('fs');
    fs.writeFileSync(`/opt/ci/chromium-pool/ws-${process.env.PW_PORT}.txt`, server.wsEndpoint());
})();
```

### 2. Add to post-run hook in `jupyter-pool.sh`

```bash
pool_start_chromium() {
    mkdir -p /opt/ci/chromium-pool
    # One Chromium per pw-jupyter — shared browser, separate contexts
    # Actually: single Chromium with multiple contexts is fine
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PW_PORT=3001 node /opt/ci-runner/browser-server.js &
    echo $! > /opt/ci/chromium-pool/pid
}

pool_check_chromium() {
    [[ ! -f /opt/ci/chromium-pool/ws-3001.txt ]] && return 1
    local ws_url
    ws_url=$(cat /opt/ci/chromium-pool/ws-3001.txt)
    # Health check: try CDP /json/version
    curl -sf "http://localhost:3001/json/version" >/dev/null 2>&1 || return 1
    return 0
}
```

### 3. Playwright config: CI variant

Add to `packages/buckaroo-js-core/playwright-jupyter.config.ts` (or create CI overlay):

```typescript
// Only connect to pre-started browser when env var is set
const connectOptions = process.env.PW_BROWSER_WS
    ? { wsEndpoint: process.env.PW_BROWSER_WS }
    : undefined;

export default defineConfig({
    use: {
        ...connectOptions,
        // ...existing config...
    },
});
```

**Open question:** Playwright's `connectOptions` applies to all workers — they all share
one Chromium. Each worker gets its own `BrowserContext` (isolated). This is fine for test
isolation but means all 9 workers share one Chromium process. If test isolation requires
separate browser *processes*, we'd need 9 Chromium servers on 9 ports.

For now: start with 1 shared Chromium (simpler, lower memory). If tests flake due to
shared process, split to 9.

### 4. Wire into `test_playwright_jupyter_parallel.sh`

When pool has Chromium ready, set `PW_BROWSER_WS` env var before calling Playwright:
```bash
if [[ -f /opt/ci/chromium-pool/ws-3001.txt ]]; then
    export PW_BROWSER_WS=$(cat /opt/ci/chromium-pool/ws-3001.txt)
fi
```

---

## Validation

1. Run with pre-started Chromium. Compare pw-jupyter timing vs baseline.
2. Kill Chromium between runs. Verify fallback to local launch.
3. Check test isolation: ensure no state leaks between workers.

## Risks

- Chromium process crash → one test failure cascades to all 9 workers.
  Mitigation: health check; fallback to local launch.
- Playwright version mismatch between pre-started Chromium and test runner.
  Mitigation: version check in pool_check_chromium.
