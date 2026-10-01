# HackEval: Secure & Auditable Classification Hackathon Evaluation Platform

HackEval is an enterprise-grade, secure, and fully auditable evaluation platform for competitive classification hackathons. It automates participant submission ingestion, deterministic scoring against isolated private ground truth, official submission selection, top-20 finalist endpoint verification with hardened SSRF protection, numerical final score calculation, and authenticated Model Context Protocol (MCP) administration.

---

## 1. Approved Competition Configuration

The following YAML is the canonical application configuration. In production mode, competition-specific values marked `TODO` must be approved and supplied by the organizers before live competition launch.

```yaml
competition:
  name: "HackEval Classification Challenge"
  timezone: "Asia/Kolkata"
  problem_type: "single_label_classification"

  submission:
    max_attempts_per_team: 5
    selection_policy: "best_valid_preliminary_score"
    deadline_utc: "TODO"
    reject_submissions_after_deadline: true
    freeze_official_submission: true

    # Do not expose scores calculated against private labels
    # while participants can still submit replacement attempts.
    reveal_preliminary_scores_before_deadline: false

    require_excel_file: true
    accepted_extensions:
      - ".xlsx"

    require_https_endpoint: true
    require_deployment_version: true
    require_endpoint_freeze_declaration: true

  evaluation:
    case_id_column: "case_id"
    prediction_column: "prediction"
    expected_prediction_type: "string"
    label_set: "TODO"
    expected_case_count: "TODO"

    preliminary_dataset_version: "TODO"
    finalist_test_set_version: "TODO"
    scoring_policy_version: "classification-v1"

    invalid_submission_policy: "ineligible"
    missing_prediction_policy: "ineligible"
    duplicate_case_id_policy: "ineligible"
    unexpected_case_id_policy: "ineligible"

    preliminary_metric: "accuracy"
    final_predictive_metric: "accuracy"

    finalist_count: 20
    verification_uses_fresh_hidden_cases: true
    equal_test_protocol_for_all_finalists: true

  final_scoring:
    qualitative_review_enabled: false

    # Proposed weights preserve the original 70:15 ratio
    # between predictive performance and reliability.
    # Organizers must approve them before the competition opens.
    verified_performance_weight: 0.823529
    reliability_weight: 0.176471

    score_range_min: 0
    score_range_max: 100

    performance_metric: "hidden_test_accuracy"
    reliability_metric: "valid_response_rate"

    tie_breakers:
      - "verified_performance"
      - "reliability_score"
      - "TODO_organizer_approved_final_tiebreaker"

  finalist_verification:
    hosting_model: "participant_managed"
    concurrency_limit: 5
    connect_timeout_seconds: 5
    read_timeout_seconds: 20
    max_retries: 1
    max_response_bytes: 1048576
    max_batch_size: "TODO"
    total_verification_deadline_seconds: "TODO"

    retry_policy_version: "verification-v1"
    endpoint_safety_policy_version: "ssrf-policy-v1"
    deployment_version_must_match: true

  qualitative_review:
    enabled: false
    llm_may_change_numeric_scores: false

  publication:
    preliminary_leaderboard_is_provisional: true
    final_publication_requires_admin_approval: true
    published_results_are_immutable: true
```

---

## 2. Core Architecture & System Design

```
+---------------------------------------------------------------------------------+
|                                 HackEval Web UI                                 |
|          Participant Portal  |  Provisional Leaderboard  |  Admin Console       |
+----------------------------------------+----------------------------------------+
                                         | REST API (HTTPS / JSON)
                                         v
+---------------------------------------------------------------------------------+
|                            FastAPI Evaluation Backend                           |
|  - Auth & RBAC (Participant, Admin)        - Submission Ingestion Engine        |
|  - Deterministic Preliminary Evaluator     - Leaderboard Freeze & Publishing    |
|  - MCP Admin Tools Bridge                  - Audit Logging & Evidence Storage   |
+-------------------+--------------------+--------------------+-------------------+
                    |                    |                    |
                    v                    v                    v
         +--------------------+  +---------------+  +--------------------+
         | PostgreSQL / DB    |  | Redis / Queue |  | Private Object     |
         | (Audit, State,     |  | (Verification |  | Storage (Encrypted |
         |  Leaderboards)     |  |  Jobs)        |  |  Ground Truth)     |
         +--------------------+  +-------+-------+  +--------------------+
                                         |
                                         v
         +---------------------------------------------------------------+
         |             Hardened Finalist Verification Worker             |
         |  - Strict Multi-layer SSRF Defense (DNS, IP ranges, pinning)   |
         |  - Fresh Hidden Test Case Ingestion                           |
         |  - Version Verification & Latency Tracking                    |
         |  - Immutable Evidence Archival                                |
         +-------------------------------+-------------------------------+
                                         | HTTPS (SSRF-Filtered)
                                         v
         +---------------------------------------------------------------+
         |                Participant-Hosted Endpoints                   |
         +---------------------------------------------------------------+
```

### Components

1. **API Server (`backend/app`)**: Built with FastAPI, handling REST requests, file uploads, schema validation, submission locking, and authentication.
2. **Deterministic Evaluator**: In-memory, streaming Excel parser that calculates accuracy using `case_id` hash joins against private ground truth without writing raw predictions or labels to disk.
3. **SSRF-Defended Worker**: High-assurance HTTP client verifying external participant endpoints against DNS rebinding, internal IP ranges (RFC1918, RFC6598, link-local, loopback, IPv6 mapped, cloud metadata), enforced timeouts, and strict content length limits.
4. **Python MCP Server (`backend/app/mcp_server.py`)**: Official Python Model Context Protocol server exposing administrative tools with token authentication, idempotency, and audit trails.
5. **Modern Dashboard (`frontend/`)**: React/Next.js frontend with live countdown, submission tracking, provisional preliminary leaderboard, finalist verification monitoring, and admin publication workflow.

---

## 3. Official Submission Selection Rule

1. Submissions close strictly at `deadline_utc`. Any submission received after the deadline is rejected.
2. For each registered team, consider only submissions that:
   - Passed schema validation.
   - Were received before the deadline.
3. For each team, select the valid submission with the highest preliminary accuracy against the frozen preliminary dataset.
4. **Deterministic Tie-Breakers**:
   - Tie-breaker 1: Later submission timestamp (`created_at` UTC).
   - Tie-breaker 2: Submission UUID (lexicographical string sort).
5. At the deadline, the preliminary leaderboard is frozen as **Provisional**.
6. The top 20 eligible teams are selected as **Finalists**.

---

## 4. Final Scoring Formula

Qualitative AI-assisted review is strictly disabled. The final score is 100% deterministic and calculated as:

$$S_{\text{final}} = 0.823529 \cdot P + 0.176471 \cdot R$$

Where:
- $P$ is the finalist hidden-test accuracy on fresh, unreleased cases, normalized to 0–100:
  $$P = \frac{\text{Correct Hidden Predictions}}{\text{Total Hidden Cases}} \times 100$$
- $R$ is the reliability score normalized to 0–100:
  $$R = \frac{\text{Valid Responses within Timeout}}{\text{Total Verification Requests}} \times 100$$

Any request resulting in connect/read timeout (>5s / >20s), HTTP non-200, malformed JSON, mismatched deployment version, or missing `case_id` prediction counts as an invalid response.

---

## 5. Security & SSRF Defense Architecture

Participant endpoints are untrusted. The verification worker enforces:
1. **URL Scheme Enforcement**: Only `https://` is allowed.
2. **DNS Resolution & Rebinding Defense**: Hostnames are resolved before connection. Resolved IPs are verified against blacklisted ranges:
   - `0.0.0.0/8`, `10.0.0.0/8`, `127.0.0.0/8`, `169.254.0.0/16`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10`
   - IPv6 equivalents (`::1`, `fe80::/10`, `fc00::/7`, `::ffff:0:0/96`)
   - Cloud metadata IP: `169.254.169.254` and `metadata.google.internal`
3. **Direct IP Pinning**: Requests connect directly to the verified IP with TLS Server Name Indication (SNI) to prevent DNS rebinding between check and connect.
4. **Redirect Prohibition**: Automatic HTTP redirects are disabled.
5. **Payload Bounds**: Max 1MB response body, strict JSON schema validation.

---

## 6. Model Context Protocol (MCP) Tools

The authenticated MCP server exposes the following administrative tools:

| Tool Name | Parameters | Description |
|-----------|------------|-------------|
| `get_competition_status` | `admin_token` | Retrieves current competition lifecycle status, submission count, and configuration state. |
| `freeze_and_select_official` | `admin_token`, `deadline_override_iso?` | Freezes open submissions, deterministically selects official attempts per team, and freezes the provisional leaderboard. |
| `get_preliminary_leaderboard` | `admin_token`, `limit?` | Fetches the frozen preliminary leaderboard with rank and qualification status. |
| `trigger_finalist_verification` | `admin_token`, `finalist_ids?` | Enqueues verification runs for top-20 finalists. |
| `get_verification_status` | `admin_token`, `job_id?` | Checks verification progress, latency metrics, and reliability results. |
| `calculate_final_scores` | `admin_token` | Deterministically calculates final scores using the approved formula ($0.823529P + 0.176471R$). |
| `publish_final_leaderboard` | `admin_token`, `notes` | Officially approves and permanently freezes the final leaderboard. |
| `get_audit_trail` | `admin_token`, `action?`, `limit?` | Retrieves immutable audit logs for evaluation decisions. |

---

## 7. Rules Requiring Organizer Approval Before Launch

The platform will operate in development mode with synthetic validation until organizers confirm:
1. Exact submission deadline (`deadline_utc`) and timezone semantics.
2. Classification label set (e.g. `["class_a", "class_b", "class_c"]`) and normalization rules.
3. Expected case count and case ID format in the preliminary set.
4. Dataset versions (`preliminary_dataset_version`, `finalist_test_set_version`).
5. Fresh hidden test case count and batch size for finalist verification.
6. Endpoint request authentication tokens/headers (if required).
7. Formal reliability penalty schedule for retried vs failed requests.
8. Approved 3rd-tier tie-breaker after performance and reliability.
9. Official procedure for participant deployment freeze declarations.
10. Final scoring weights ratification (proposed $0.823529 : 0.176471$).
11. Data retention and participant dispute resolution policies.
