# HackEval Operational Runbook

This runbook defines standard operating procedures (SOPs) for the HackEval platform before, during, and after a competitive classification hackathon.

---

## 1. Pre-Launch Checklist & Organizer Decision Sign-off

Before launching a live competition with participant access, ensure that all 11 competition-specific decisions have been supplied and signed off in `competition_config.yaml`:

1. **Submission Deadline**: `deadline_utc` configured in ISO 8601 UTC format.
2. **Label Set**: `label_set` defined with all allowable classification categories.
3. **Expected Case Count**: `expected_case_count` matching preliminary ground truth.
4. **Dataset Versions**: `preliminary_dataset_version` and `finalist_test_set_version` hashes locked.
5. **Batch Size & Limits**: `max_batch_size` (e.g., 25) and `total_verification_deadline_seconds` (e.g., 1800).
6. **Authentication Headers**: Confirm any endpoint authentication headers or shared secrets.
7. **Reliability Formula**: Confirm retry count (`max_retries: 1`) and timeout schedule (`connect: 5s`, `read: 20s`).
8. **Approved Tie-Breakers**:
   - 1st tier: Verified hidden-test performance ($P$).
   - 2nd tier: Reliability score ($R$).
   - 3rd tier: Approved organizer tie-breaker (e.g. lowest average latency).
9. **Deployment Freeze Protocol**: Confirm participants understand the version binding and HTTPS requirement.
10. **Final Scoring Weights**: Proposed weights approved ($0.823529 : 0.176471$).
11. **Dispute & Evidence Policy**: Verify private storage path for verification JSON evidence logs.

---

## 2. Environment Deployment

### Local Development / Quick Test
```bash
# 1. Activate Python virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Run Database Migrations
alembic upgrade head

# 3. Start Backend API
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Start Frontend
cd frontend
npm run dev
```

### Production Docker Compose Deployment
```bash
# Start all services (PostgreSQL, Redis, API, Worker, MCP Server, Frontend)
docker-compose up -d --build

# Inspect logs
docker-compose logs -f backend worker

# Check health
curl http://localhost:8000/health
```

---

## 3. Submissions Phase Operations

- **Attempt Limit**: Platform automatically limits each team to a maximum of 5 attempts.
- **Privacy Enforcement**: While submissions remain open, preliminary accuracy and private ground truth are never revealed to participants. Participants only see schema validation feedback.
- **Audit Monitoring**:
  Inspect incoming attempts and checksums:
  ```bash
  GET /api/admin/submissions
  ```

---

## 4. Deadline Freeze & Official Selection SOP

When the competition deadline arrives:
1. **Trigger Freeze via Admin Console or MCP**:
   - Web Console: Navigate to **Admin Control Center** -> Click **Execute Selection**.
   - Or via MCP Tool:
     ```python
     freeze_and_select_official(admin_token="<ADMIN_API_KEY>")
     ```
2. **System Actions**:
   - Rejects any further submissions.
   - Evaluates all valid attempts submitted prior to cutoff.
   - Selects the official attempt per team using highest preliminary accuracy.
   - Applies deterministic tie-breakers:
     - Tie-breaker 1: Later submission timestamp (`submitted_at` UTC).
     - Tie-breaker 2: Submission UUID (lexicographical sort).
   - Freezes the provisional preliminary leaderboard.
   - Identifies and freezes the Top 20 Finalists.

---

## 5. Finalist Verification SOP

1. **Verify Reachability & Version**:
   - Workers ping `{endpoint_url}/health` or main endpoint.
   - Confirms reported version matches declared deployment version.
2. **Run Verification Jobs**:
   - Admin Console: Click **Run Verification**.
   - Or via MCP Tool:
     ```python
     trigger_finalist_verification(admin_token="<ADMIN_API_KEY>")
     ```
   - Outbound requests strictly enforce SSRF protection (DNS pre-resolution, private IP blocking, loopback blocking, cloud metadata blocking, no redirects, 1MB response limit).
   - Hidden test cases are sent in batches of 25.
3. **Inspect Verification Evidence**:
   Verification evidence logs are written to `data/storage/evidence/finalist_<id>/` with full request and response audit logs.

---

## 6. Final Score Calculation & Publication SOP

1. **Preview Scores**:
   ```python
   calculate_final_scores(admin_token="<ADMIN_API_KEY>")
   ```
   Formula:
   $$S_{\text{final}} = 0.823529 \cdot P + 0.176471 \cdot R$$
   Qualitative AI judging is strictly disabled.
2. **Organizer Sign-Off & Immutable Publication**:
   - Admin Console: Click **Approve & Publish** and enter sign-off notes.
   - Or via MCP Tool:
     ```python
     publish_final_leaderboard(admin_token="<ADMIN_API_KEY>", notes="Signed off by Lead Judge")
     ```
   - Once published, results are marked `is_immutable: true` and cannot be altered or overwritten.
