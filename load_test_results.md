# HackEval Synthetic Load Test Results

## 1. Test Configuration
- **Total Teams**: 4,000
- **Attempts per Team**: 5
- **Total Submissions Ingested & Evaluated**: 20,000
- **Preliminary Test Cases per Submission**: 500
- **Total In-Memory Classification Comparisons**: 10,000,000

## 2. Measured Performance Metrics
| Metric | Measured Value |
|---|---|
| **Total Evaluation Time** | 1.16 seconds |
| **Sustained Ingestion & Evaluation Throughput** | **17254.41 submissions/sec** |
| **Latency (p50)** | 0.06 ms |
| **Latency (p95)** | 0.06 ms |
| **Latency (p99)** | 0.09 ms |
| **Memory Consumption Delta** | 10.21 MB |
| **Official Selection Runtime (4,000 teams)** | **4.66 ms** |

## 3. Queue & Resource Behavior Analysis
- **CPU & Memory Scaling**: Memory growth remained sub-linear and stabilized at ~10.2 MB due to in-memory streaming validation.
- **Selection Determinism**: 4,000 teams were filtered, tied-broken, and ranked in under 4.7 ms with zero floating-point discrepancies.
- **System Capacity**: The platform comfortably processes 20,000 submissions in ~1.2 seconds on a single core, well within any real-time hackathon submission deadline surge.
