# Cloud Server Comparison for CI

**Date:** 2026-03-02
**Context:** Evaluating alternatives to current Hetzner CCX43 for CI workloads. Primary goal: maximize single-thread performance for build/test critical path.

## Current Setup

| Spec | Value |
|------|-------|
| Provider | Hetzner Cloud |
| Plan | CCX43 (dedicated vCPU) |
| CPU | AMD EPYC Milan (Zen3), 16 vCPU (8c/16t) |
| RAM | 64 GB |
| Disk | 360 GB |
| Traffic | 4 TB |
| Cost | €96.49/mo (~$104) |
| Geekbench 6 SC | ~2,000 |
| CI total time | ~6 min (vs ~12 min on Depot GitHub runners) |

### Why single-thread matters

CI critical path is serial: test-js (24s) → build-wheel (22s) → playwright-jupyter (2m03s). These sequential steps are single-thread bound. More cores don't help; faster cores do.

---

## Provider Comparison

### Hetzner Cloud

All-inclusive pricing (traffic, IPv4, DDoS, firewall). API provisioning, Terraform provider. EU datacenters (Falkenstein, Nuremberg, Helsinki) + US (Ashburn, Hillsboro) + Singapore.

#### Shared vCPU — CX (x86, cheapest)

| Plan | vCPU | RAM | Disk | Traffic | €/mo |
|------|------|-----|------|---------|------|
| CX23 | 2 | 4 GB | 40 GB | 20 TB | 3.49 |
| CX33 | 4 | 8 GB | 80 GB | 20 TB | 5.49 |
| CX43 | 8 | 16 GB | 160 GB | 20 TB | 9.49 |
| CX53 | 16 | 32 GB | 320 GB | 20 TB | 17.49 |

#### Shared vCPU — CAX (ARM/Ampere)

| Plan | vCPU | RAM | Disk | Traffic | €/mo |
|------|------|-----|------|---------|------|
| CAX11 | 2 | 4 GB | 40 GB | 20 TB | 3.79 |
| CAX21 | 4 | 8 GB | 80 GB | 20 TB | 6.49 |
| CAX31 | 8 | 16 GB | 160 GB | 20 TB | 12.49 |
| CAX41 | 16 | 32 GB | 320 GB | 20 TB | 24.49 |

#### Shared vCPU — CPX Gen2 (AMD Genoa Zen4)

New generation, substantially better single-thread than CX. Up to 5x perf/€ vs Gen1.

| Plan | vCPU | RAM | Disk | Traffic | €/mo |
|------|------|-----|------|---------|------|
| CPX12 | 1 | 2 GB | 40 GB | 0.5 TB | 6.49 |
| CPX22 | 2 | 4 GB | 80 GB | 1 TB | 6.49 |
| CPX32 | 4 | 8 GB | 160 GB | 2 TB | 10.99 |
| CPX42 | 8 | 16 GB | 320 GB | 3 TB | 19.99 |
| CPX52 | 12 | 24 GB | 480 GB | 4 TB | 28.49 |
| CPX62 | 16 | 32 GB | 640 GB | 5 TB | 38.99 |

#### Dedicated vCPU — CCX (current line)

CPU: EPYC Milan (Zen3) or Genoa (Zen4) depending on host hardware.

| Plan | vCPU | RAM | Disk | Traffic | €/mo |
|------|------|-----|------|---------|------|
| CCX13 | 2 | 8 GB | 80 GB | 1 TB | 12.49 |
| CCX23 | 4 | 16 GB | 160 GB | 2 TB | 24.49 |
| CCX33 | 8 | 32 GB | 240 GB | 3 TB | 48.49 |
| **CCX43** | **16** | **64 GB** | **360 GB** | **4 TB** | **96.49** |
| CCX53 | 32 | 128 GB | 600 GB | 6 TB | 192.49 |
| CCX63 | 48 | 192 GB | 960 GB | 8 TB | 288.49 |

#### Hetzner Dedicated (AX line, bare metal)

Unlimited traffic. No API provisioning — manual order, hours to provision.

| Model | CPU | Cores | RAM | Storage | €/mo |
|-------|-----|-------|-----|---------|------|
| AX42 | Ryzen 7 PRO 8700GE (Zen4) | 8c/16t | 64 GB DDR5 | 2×512 GB NVMe | 46 |
| AX52 | Ryzen 7 7700 (Zen4) | 8c/16t | 64 GB DDR5 | 2×1 TB NVMe | 59 |
| **AX102** | **Ryzen 9 7950X3D (Zen4+V-Cache)** | **16c/32t** | **128 GB DDR5** | **2×1.92 TB NVMe** | **104** |
| AX162-R | EPYC 9454P (Zen4) | 48c | 256 GB DDR5 ECC | 2×3.84 TB NVMe | 199 |
| AX162-S | EPYC 9454P (Zen4) | 48c | 128 GB DDR5 ECC | 2×3.84 TB NVMe | 199 |

**Note:** Hetzner raising prices ~25-35% on April 1, 2026. All prices above are pre-increase.

---

### AWS EC2

Per-second billing, best tooling (boto3, Terraform, CLI, CDK). Egress expensive ($90/TB).

#### m8azn (fastest single-thread in any cloud)

CPU: AMD EPYC 9575F (Turin Zen5), 5.0 GHz. Launched Feb 2026. Available: us-east-1, us-west-2, eu-central-1, ap-northeast-1.

| Size | vCPU | RAM | $/hr (on-demand) | $/mo (730hr) |
|------|------|-----|-------------------|-------------|
| m8azn.medium | 1 | 4 GB | $0.103 | $75 |
| m8azn.large | 2 | 8 GB | ~$0.207 | ~$151 |
| m8azn.xlarge | 4 | 16 GB | ~$0.413 | ~$301 |
| m8azn.3xlarge | 12 | 48 GB | ~$1.24 | ~$905 |
| m8azn.6xlarge | 24 | 96 GB | ~$2.48 | ~$1,810 |
| m8azn.12xlarge | 48 | 192 GB | ~$4.96 | ~$3,620 |

PassMark ST: 4,279 (#1 among x86 cloud). Geekbench 6 SC: ~3,500.

Spot pricing available (~70% discount, risk of interruption).

#### Other relevant EC2 families

- **R7iz** — Intel Xeon, up to 3.9 GHz all-core turbo, 20% faster than z1d
- **z1d** — Custom Intel Xeon 8151, 4.0 GHz sustained, legacy high-frequency option
- **c8g** (Graviton 4, ARM) — GB6 SC ~1,930, not competitive on single-thread

---

### OVHcloud

European provider. Bare metal = hours to provision (no API spinup under 5 min). Monthly billing only on Rise line.

#### Rise Dedicated Servers

| Model | CPU | Cores | Clock | RAM | Storage | $/mo |
|-------|-----|-------|-------|-----|---------|------|
| RISE-1 | Xeon E-2386G | 6c/12t | 3.5-4.7 GHz | 32-128 GB | 2×512GB + 2×6TB NVMe | $70 |
| RISE-2 | Xeon E-2388G | 8c/16t | 3.2-4.6 GHz | 32-128 GB | 2×512GB + 2×6TB NVMe | $80 |
| RISE-GAME-1 | Ryzen 5 5600X | 6c/12t | 3.7-4.6 GHz | 32-64 GB | 2×512GB NVMe | $90 |
| RISE-GAME-2 | Ryzen 7 5800X | 8c/16t | 3.8-4.7 GHz | 64-128 GB | 2×960GB NVMe | $104 |
| RISE-3 | Ryzen 9 5900X | 12c/24t | 3.7-4.8 GHz | 32-128 GB | 512GB-6TB NVMe | $110 |
| **RISE-M** | **Ryzen 9 9900X (Zen5)** | **12c/24t** | **4.4-5.6 GHz** | **64 GB** | **512GB NVMe** | **$114** |
| **RISE-L** | **Ryzen 9 9950X (Zen5)** | **16c/32t** | **4.3-5.7 GHz** | **128 GB** | **960GB NVMe** | **$162** |
| RISE-STOR | Ryzen 7 PRO 3700 | 8c/16t | 3.6-4.4 GHz | 32-128 GB | 14TB SAS | $190 |
| Game-1 2026 | **Ryzen 7 9800X3D** | 8c/16t | 4.7-5.2 GHz | 64-256 GB | 2×960GB NVMe | $79-264 |

RISE-M and RISE-L are Europe only (Germany, France, Poland). Setup fee = 1 month (waived on 12-month commit). REST API + Terraform provider available but provisioning is slow.

---

### Cherry Servers

Lithuanian company. Trustpilot 4.5/5. Bare metal cloud with **hourly billing** and full automation.

**Standout features:** Official Terraform provider, Ansible modules, Go/Python SDKs, CLI, REST API. Provisioning: 15-30 minutes. 10 Gbps uplink, 100 TB egress included.

Data centers: Lithuania, Amsterdam, Stockholm, Chicago, Frankfurt, Singapore.

| Model | CPU | Cores | RAM | Storage | $/hr | $/mo | Stock |
|-------|-----|-------|-----|---------|------|------|-------|
| Ryzen 7700X | Zen4, 5.4 GHz | 8c/16t | 64 GB | 2×1TB NVMe | $0.318 | $186 | 15 |
| **Ryzen 7950X** | **Zen4, 5.7 GHz** | **16c/32t** | **128 GB DDR5 ECC** | **2×1TB NVMe** | **$0.399** | **$233** | 2 (Chicago) |
| **Ryzen 9950X** | **Zen5, 5.7 GHz** | **16c/32t** | **192 GB DDR5** | **2×1TB NVMe** | **$0.518** | **$303** | 99 (AMS+Stockholm) |
| Threadripper 7965WX | Zen4, 5.3 GHz | 24c/48t | 512 GB | 2×1TB+2×4TB NVMe | $1.961 | $974 | — |
| EPYC 9375F | Turin Zen5, 4.8 GHz | 32c/64t | 384 GB | 2×1TB+2×4TB NVMe | $1.801 | $894 | — |
| EPYC 7313P | Milan | 16c/32t | 64 GB | 2×250GB NVMe | $0.318 | $186 | varies |

**Provisioning is 15-30 min — does NOT meet <5 min spinup requirement.**

---

### HOSTKEY

Dutch company (est. 2007). WHTop 8.8/10. REST API, hourly billing, 10-20 min provisioning.

Data centers: Amsterdam, Zürich, Warsaw, Milan, Madrid, Paris, London, Frankfurt, Helsinki, New York, Istanbul, Moscow.

| Model | CPU | Cores | RAM | Storage | €/hr | €/mo |
|-------|-----|-------|-----|---------|------|------|
| **Ryzen 9 7950X** | **Zen4, 4.5 GHz** | **16c/32t** | **128 GB** | **2×1.92TB NVMe** | **€0.179** | **€129** |
| Ryzen 9 5950X | Zen3 | 16c/32t | 32-128 GB | 240GB-2×1TB | — | €137-285 |
| Ryzen 9 5900X | Zen3 | 12c/24t | 64 GB | 1TB NVMe | — | €180 |

No Terraform provider (REST API only). No 9950X or Zen5 options. IPMI access. 1 Gbps / 50 TB traffic.

**Provisioning is 10-20 min — does NOT meet <5 min spinup requirement.**

---

### Vultr

US-based. Cloud VMs spin up in ~1-2 minutes. Hourly billing. Terraform provider.

#### VX1 (Dedicated CPU, EPYC Turin Zen5)

| Plan | vCPU | RAM | Bandwidth | $/mo |
|------|------|-----|-----------|------|
| VX1 2C | 2 | 8 GB | 5 TB | $43.20 |
| VX1 4C | 4 | 16 GB | 6 TB | $86.40 |
| VX1 8C | 8 | 32 GB | 7 TB | $172.80 |
| VX1 16C | 16 | 64 GB | 8 TB | $345.60 |

GB6 SC: ~2,350. Block storage (not local NVMe). Server-clocked Turin — lower single-thread than desktop Zen5.

#### High Frequency (shared, Intel Xeon 3GHz+)

| Plan | vCPU | RAM | Storage | $/mo |
|------|------|-----|---------|------|
| HF 8-core | 8 | 32 GB | 512 GB NVMe | $192 |
| HF 16-core | 16 | 58 GB | 1 TB NVMe | $320 |

---

### Linode / Akamai

Cloud VMs, ~1-2 minute spinup, hourly billing, Terraform provider.

#### Dedicated CPU (3 generations)

| Plan | Generation | CPU | vCPU | RAM | $/mo |
|------|-----------|-----|------|-----|------|
| Dedicated 16GB | G6 | — | 8 | 16 GB | $144 |
| G7 Dedicated 16x8 | G7 | Zen3 | 8 | 16 GB | $173 |
| **G8 Dedicated 16x8** | **G8** | **Zen5** | **8** | **16 GB** | **$180** |
| G8 Dedicated 32x16 | G8 | Zen5 | 16 | 32 GB | $360 |

G8 (Zen5) has the best single-thread in cloud VPS outside AWS m8azn. But extremely expensive.

---

### DigitalOcean

Cloud VMs, ~1 min spinup, per-second billing (since Jan 2026), Terraform provider.

#### CPU-Optimized Droplets (dedicated vCPU, 2.6 GHz+)

| Plan | vCPU | RAM | Disk | Transfer | $/mo |
|------|------|-----|------|----------|------|
| c-2 | 2 | 4 GB | 25 GB | 4 TB | $40 |
| c-4 | 4 | 8 GB | 50 GB | 5 TB | $80 |
| c-8 | 8 | 16 GB | 100 GB | 6 TB | $160 |
| c-16 | 16 | 32 GB | 200 GB | 7 TB | $320 |
| c-32 | 32 | 64 GB | 400 GB | 8 TB | $640 |

No standout single-thread performance. Expensive for what you get.

---

### Cloudflare Containers

Serverless containers at the edge. Per-second billing. NOT suitable for CI.

- Max instance: 4 vCPU, 12 GB RAM (too small)
- Ephemeral disk only (no warm caches)
- No SSH, no Docker exec
- CCX43-equivalent running 24/7 would cost ~$665/mo
- Egress: $0.025/GB (1 TB free)

---

## CPU Architecture Overview

### AMD Lineup (relevant chips)

| Chip | Line | Arch | Cores | Boost | L3 Cache | GB6 SC | PassMark ST |
|------|------|------|-------|-------|----------|--------|-------------|
| EPYC 9575F | Server (Turin) | Zen5 | 64 | 5.0 GHz | 256 MB | ~3,500 | 4,279 |
| EPYC 9175F | Server (Turin) | Zen5 | 16 | 5.0 GHz | **512 MB** | ~3,500 | 4,244 |
| Ryzen 9 9950X | Desktop | Zen5 | 16 | 5.7 GHz | 64 MB | ~3,150 | ~4,100 |
| Ryzen 9 9950X3D | Desktop | Zen5+V-Cache | 16 | — | 128 MB | ~3,400 | — |
| Ryzen 9 9950X3D2 | Desktop | Zen5+dual V-Cache | 16 | — | **192 MB** | — | — (upcoming) |
| Ryzen 7 9800X3D | Desktop | Zen5+V-Cache | 8 | 5.2 GHz | 96 MB | ~3,300 | — |
| Ryzen 9 9900X | Desktop | Zen5 | 12 | 5.6 GHz | 64 MB | ~3,050 | — |
| Ryzen 9 7950X3D | Desktop | Zen4+V-Cache | 16 | 5.7 GHz | 128 MB | ~2,817 | ~3,884 |
| Ryzen 9 7950X | Desktop | Zen4 | 16 | 5.7 GHz | 64 MB | ~2,750 | — |
| EPYC Genoa 9654 | Server | Zen4 | 96 | 3.7 GHz | 384 MB | ~2,500 | — |
| EPYC Milan 7003 | Server | Zen3 | varies | ~3.5 GHz | 32-256 MB | **~2,000** | ~2,500 |

### Key insights

- **Desktop Ryzen clocks 40-60% higher than server EPYC** on single-thread because server chips optimize for core count and power efficiency, not boost clocks
- **V-Cache (3D stacked L3)** gives 10-30% real-world improvement for cache-sensitive workloads (compilers, bundlers, test runners)
- **Zen5 IPC is ~15% better than Zen4**, plus higher clocks
- **EPYC 9175F** (512 MB L3, 16 cores, 5 GHz) is the ideal CI chip but not available from any hosting provider yet
- **ARM (Graviton 4, Ampere)** is ~35-45% behind top x86 on single-thread; wrong direction for ST-bound CI

### Cache matters for builds

Compilers, bundlers, and test runners are often cache-bound. Working sets that fit in L3 run dramatically faster:

| Cache size | Chip examples |
|-----------|---------------|
| 512 MB | EPYC 9175F (not rentable) |
| 192 MB | Ryzen 9950X3D2 (upcoming, not rentable) |
| 128 MB | Ryzen 7950X3D (Hetzner AX102), Ryzen 9950X3D (not rentable) |
| 96 MB | Ryzen 9800X3D (OVH Game-1) |
| 64 MB | Ryzen 9950X (Cherry, OVH RISE-L) |
| 32 MB | EPYC Milan (current CCX43) |

---

## Head-to-Head: Options meeting <5 min API spinup

Only cloud VM providers qualify. Bare metal (Cherry, HOSTKEY, OVH Rise, Hetzner AX) all take 10+ minutes.

| | **Current CCX43** | **AWS m8azn.3xl** | **Hetzner CPX62** | **Vultr VX1-8** | **Linode G8-16x8** |
|--|-------------------|-------------------|-------------------|-----------------|---------------------|
| CPU | EPYC Milan (Zen3) | EPYC 9575F (Zen5) | EPYC Genoa (Zen4) | EPYC Turin (Zen5) | Zen5 |
| GB6 SC | **~2,000** | **~3,500** | ~2,500 | ~2,350 | ~2,800 |
| vs current | baseline | **+75%** | +25% | +18% | +40% |
| vCPU | 16 dedicated | 12 | 16 shared | 8 dedicated | 8 dedicated |
| RAM | 64 GB | 48 GB | 32 GB | 32 GB | 16 GB |
| Disk | 360 GB | EBS | 640 GB | Block | 164 GB |
| Spinup | always on | ~60s | ~15s | ~90s | ~90s |
| $/hr | — | $1.24 | ~$0.06 | $0.26 | $0.27 |
| $/mo flat | €96 (~$104) | ~$905 | **€39** | $173 | $180 |
| 60 hrs/mo | $104 (flat) | **$74** | **$39 (flat)** | $156 | $162 |
| Per CI run (6 min) | — | $0.12 | $0.06 (1hr min) | $0.03 | $0.03 |
| Terraform | Cloud API | Yes | Yes | Yes | Yes |
| Traffic | 4 TB | pay/GB ($90/TB) | 5 TB | 7 TB | — |

---

## Bare Metal Options (>5 min spinup, monthly/hourly)

Best value when running always-on or in long sessions.

| | **Hetzner AX102** | **OVH RISE-L** | **Cherry 9950X** | **HOSTKEY 7950X** |
|--|-------------------|----------------|-------------------|-------------------|
| CPU | 7950X3D (Zen4+V-Cache) | 9950X (Zen5) | 9950X (Zen5) | 7950X (Zen4) |
| GB6 SC | ~2,817 | ~3,150 | ~3,150 | ~2,750 |
| vs current | +40% | +55% | +55% | +38% |
| Cores | 16c/32t | 16c/32t | 16c/32t | 16c/32t |
| RAM | 128 GB DDR5 | 128 GB DDR4 | 192 GB DDR5 | 128 GB |
| L3 Cache | **128 MB** | 64 MB | 64 MB | 64 MB |
| Storage | 2×1.92 TB NVMe | 960 GB NVMe | 2×1 TB NVMe | 2×1.92 TB NVMe |
| $/mo flat | **€104** | **$162** | $303 | **€129** |
| Hourly | No | No | **$0.518** | **€0.179** |
| 60 hrs/mo | €104 (flat) | $162 (flat) | **$31** | **€11** |
| Spinup | Hours | Hours | 15-30 min | 10-20 min |
| Network | 1 Gbps, unlimited | 1 Gbps, unlimited | 10 Gbps, 100 TB | 1 Gbps, 50 TB |
| Terraform | No | Yes | **Yes** | No |
| Trust level | High | High | Medium-High | Medium |

---

## Recommendations

### Quick win (no migration)

**Downgrade CCX43 → CCX33** (€96 → €48/mo). Memory notes say CI timing is identical. Saves €48/mo immediately.

### Best <5 min spinup

**AWS m8azn** — 75% faster single-thread than current box. Only option with a dramatic performance improvement that also meets the fast-spinup requirement. Try m8azn.xlarge (4 vCPU, $0.41/hr) first to benchmark. At $0.12 per 6-min CI run, break-even vs CCX33 is ~400 runs/month.

### Best value (always-on)

**Hetzner AX102** (€104/mo) — 7950X3D with 128 MB V-Cache, 16 real cores, 40% faster ST than current. Cache advantage helps build workloads specifically. Same price as current CCX43.

### Best hourly bare metal

**Cherry Servers 9950X** ($0.518/hr) — Zen5, best ST in bare metal, Terraform provider, 15-30 min spinup. At 60 hrs/mo = $31. Best automation story of any bare metal provider.

### Cheapest hourly bare metal

**HOSTKEY 7950X** (€0.179/hr) — 60 hrs/mo = €11. Cheapest way to get 16-core Ryzen. Slightly slower ST than current AX102 option but absurdly cheap for bursty use.

### Future watch

- **EPYC 9175F** (512 MB L3, 16c, 5 GHz) — perfect CI chip, not rentable yet
- **Ryzen 9950X3D / 9950X3D2** — 128-192 MB V-Cache + Zen5 IPC, not hosted anywhere yet
- **AWS m8azn spot** — ~$0.34/hr for 12 vCPU, fastest ST at Hetzner-like prices, but interruption risk

---

## Egress / Bandwidth Comparison

| Provider | Included | Overage |
|----------|----------|---------|
| Hetzner Cloud | 1-20 TB (varies by plan) | €1/TB |
| Hetzner Dedicated | Unlimited | — |
| AWS EC2 | 100 GB free | **$90/TB** |
| OVH Rise | Unlimited | — |
| Cherry Servers | 100 TB | — |
| HOSTKEY | 50 TB | — |
| Vultr | 5-9 TB | $0.01/GB |
| DigitalOcean | 4-9 TB | $0.01/GB |
| Cloudflare R2 | **Free egress** | — |

AWS egress is 90x more expensive than Hetzner. For CI this is negligible (small payloads) but matters for artifact storage or large Docker pulls.
