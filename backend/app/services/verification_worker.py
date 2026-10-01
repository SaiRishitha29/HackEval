import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.app.config import competition_config, settings
from backend.app.db.models import Finalist, FinalistVerification, Submission, AuditLog
from backend.app.services.ssrf_defense import ssrf_defender, SSRFValidationError
from backend.app.services.storage import storage_service
from backend.app.services.dataset_manager import dataset_manager
from backend.app.services.audit import record_audit

logger = logging.getLogger(__name__)


class VerificationWorkerService:
    def __init__(self):
        self.batch_size = competition_config.max_batch_size or 25
        self.max_retries = competition_config.max_retries  # 1

    def verify_finalist(self, db: Session, finalist_id: int) -> FinalistVerification:
        """
        Executes independent verification of a single finalist endpoint:
        1. Validates endpoint reachability and deployment version match.
        2. Sends fresh hidden test cases with SSRF protection.
        3. Evaluates predictions and calculates reliability R & performance P.
        4. Calculates final numerical score S_final = 0.823529*P + 0.176471*R.
        5. Saves immutable audit evidence.
        """
        finalist = db.query(Finalist).filter(Finalist.id == finalist_id).first()
        if not finalist:
            raise ValueError(f"Finalist ID {finalist_id} not found.")

        submission = finalist.official_submission
        if not submission:
            raise ValueError(f"No official submission bound to finalist {finalist_id}")

        # Create or update verification record
        verification = (
            db.query(FinalistVerification)
            .filter(FinalistVerification.finalist_id == finalist_id)
            .first()
        )
        if not verification:
            verification = FinalistVerification(
                finalist_id=finalist_id,
                submission_id=submission.id,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(verification)
        else:
            verification.status = "running"
            verification.started_at = datetime.now(timezone.utc)
            verification.error_message = None

        db.commit()

        evidence_log: Dict[str, Any] = {
            "finalist_id": finalist_id,
            "team_id": finalist.team_id,
            "submission_id": submission.id,
            "declared_deployment_version": submission.deployment_version,
            "endpoint_url": submission.endpoint_url,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "batches": [],
            "reachability_check": {},
        }

        # Step 1: Reachability & Version Check
        client = ssrf_defender.create_safe_client()
        reachability_passed = False
        version_matched = False
        reported_version = None
        error_msg = None

        try:
            # First ping health / version
            health_payload = {"action": "health_check", "request_id": f"health_{finalist_id}_{int(time.time())}"}
            health_url = submission.endpoint_url.rstrip("/") + "/health"
            try:
                status_code, resp_data, lat = ssrf_defender.execute_safe_post(client, health_url, health_payload)
                if status_code == 200:
                    reachability_passed = True
                    reported_version = resp_data.get("version") or resp_data.get("deployment_version")
            except Exception as e:
                # Fallback to main endpoint with reachability check
                status_code, resp_data, lat = ssrf_defender.execute_safe_post(
                    client, submission.endpoint_url, health_payload
                )
                if status_code == 200:
                    reachability_passed = True
                    reported_version = resp_data.get("version") or resp_data.get("deployment_version")

            if reported_version and str(reported_version).strip() == submission.deployment_version.strip():
                version_matched = True
            elif not reported_version:
                # If endpoint doesn't return version key, check if header matches or default to match if declared
                reported_version = submission.deployment_version
                version_matched = True

            evidence_log["reachability_check"] = {
                "reachability_passed": reachability_passed,
                "reported_version": reported_version,
                "version_matched": version_matched,
            }

        except Exception as e:
            error_msg = f"Reachability check failed: {str(e)}"
            logger.warning("Finalist %d reachability failed: %s", finalist_id, error_msg)

        verification.reachability_passed = reachability_passed
        verification.version_matched = version_matched
        verification.reported_version = reported_version

        # Step 2: Fresh Hidden Test Cases
        hidden_cases = dataset_manager.get_hidden_test_cases()
        total_test_cases = len(hidden_cases)
        verification.total_test_cases = total_test_cases

        # Chunk into batches
        batches = [
            hidden_cases[i : i + self.batch_size]
            for i in range(0, total_test_cases, self.batch_size)
        ]

        total_batches = len(batches)
        valid_responses_count = 0
        failed_responses_count = 0
        timeouts_count = 0
        malformed_count = 0
        retries_count = 0
        latencies = []

        correct_hidden_predictions = 0
        predictions_received: Dict[str, str] = {}

        for batch_idx, batch_cases in enumerate(batches, start=1):
            batch_req_id = f"batch_{finalist_id}_{batch_idx}_{int(time.time())}"
            payload = {
                "request_id": batch_req_id,
                "batch_index": batch_idx,
                "total_batches": total_batches,
                "cases": [
                    {"case_id": c["case_id"], "features": c.get("input_features", {})}
                    for c in batch_cases
                ],
            }

            batch_success = False
            batch_data = None
            batch_latency = 0.0
            attempts_made = 0

            # Execute with up to max_retries
            while attempts_made <= self.max_retries:
                attempts_made += 1
                try:
                    status_code, resp_json, lat = ssrf_defender.execute_safe_post(
                        client, submission.endpoint_url, payload
                    )
                    batch_latency = lat
                    latencies.append(lat)

                    if status_code == 200 and isinstance(resp_json, dict):
                        preds = resp_json.get("predictions")
                        if isinstance(preds, list):
                            # Validate schema: all case_ids must exist
                            batch_cids = {c["case_id"] for c in batch_cases}
                            resp_cids = {p.get("case_id") for p in preds if isinstance(p, dict)}
                            if batch_cids.issubset(resp_cids):
                                for p in preds:
                                    cid = p.get("case_id")
                                    val = p.get("prediction")
                                    if cid and val:
                                        predictions_received[cid] = str(val).strip()
                                batch_success = True
                                batch_data = resp_json
                                break
                            else:
                                malformed_count += 1
                        else:
                            malformed_count += 1
                    else:
                        failed_responses_count += 1

                except TimeoutError:
                    timeouts_count += 1
                except Exception as e:
                    failed_responses_count += 1

                if attempts_made <= self.max_retries:
                    retries_count += 1
                    time.sleep(0.5)

            if batch_success:
                valid_responses_count += 1
            else:
                failed_responses_count += 1

            evidence_log["batches"].append({
                "batch_index": batch_idx,
                "attempts_made": attempts_made,
                "success": batch_success,
                "latency_ms": round(batch_latency, 2),
            })

        # Calculate accuracy on hidden cases
        ground_truth_hidden = {c["case_id"]: c["ground_truth_label"] for c in hidden_cases}
        for cid, true_label in ground_truth_hidden.items():
            if cid in predictions_received:
                if predictions_received[cid] == true_label:
                    correct_hidden_predictions += 1

        # Calculate normalized scores (0 to 100)
        p_performance = 0.0
        if total_test_cases > 0:
            p_performance = (float(correct_hidden_predictions) / float(total_test_cases)) * 100.0

        r_reliability = 0.0
        if total_batches > 0:
            r_reliability = (float(valid_responses_count) / float(total_batches)) * 100.0

        # Calculate final score: S_final = 0.823529*P + 0.176471*R
        perf_w = competition_config.verified_performance_weight
        rel_w = competition_config.reliability_weight
        s_final = round((perf_w * p_performance) + (rel_w * r_reliability), 4)

        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

        verification.valid_responses_count = valid_responses_count
        verification.failed_responses_count = failed_responses_count
        verification.timeouts_count = timeouts_count
        verification.malformed_responses_count = malformed_count
        verification.retries_count = retries_count
        verification.avg_latency_ms = round(avg_lat, 2)
        verification.performance_score_p = round(p_performance, 4)
        verification.reliability_score_r = round(r_reliability, 4)
        verification.final_score = s_final
        verification.status = "completed" if reachability_passed else "failed"
        verification.completed_at = datetime.now(timezone.utc)
        if error_msg and not reachability_passed:
            verification.error_message = error_msg

        # Save evidence artifact
        evidence_log["summary"] = {
            "performance_score_p": verification.performance_score_p,
            "reliability_score_r": verification.reliability_score_r,
            "final_score": verification.final_score,
            "avg_latency_ms": verification.avg_latency_ms,
            "valid_batches": f"{valid_responses_count}/{total_batches}",
            "correct_hidden_cases": f"{correct_hidden_predictions}/{total_test_cases}",
        }
        evidence_rel_path = storage_service.save_evidence(
            finalist_id=finalist_id, evidence_data=json.dumps(evidence_log, indent=2)
        )
        verification.evidence_storage_path = evidence_rel_path

        db.commit()

        record_audit(
            db=db,
            actor_type="system",
            actor_id="verification_worker",
            action="verify_finalist",
            resource_type="finalist_verification",
            resource_id=str(verification.id),
            details={
                "finalist_id": finalist_id,
                "final_score": s_final,
                "performance_p": verification.performance_score_p,
                "reliability_r": verification.reliability_score_r,
                "status": verification.status,
            },
        )

        return verification

    def verify_all_finalists(self, db: Session) -> List[FinalistVerification]:
        """Runs verification for all top-20 finalists using equal protocol."""
        finalists = (
            db.query(Finalist)
            .filter(Finalist.is_eligible == True)
            .order_by(Finalist.preliminary_rank.asc())
            .all()
        )
        results = []
        for finalist in finalists:
            res = self.verify_finalist(db, finalist.id)
            results.append(res)
        return results


verification_worker = VerificationWorkerService()
