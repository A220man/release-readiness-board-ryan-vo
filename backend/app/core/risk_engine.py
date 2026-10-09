"""Deterministic release risk index and keyword-based classification.

Deterministic risk scoring, NLP-based blocker classification,
and historical pattern detection. Works fully offline without LLM keys.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


# Keyword dictionaries for NLP-based blocker classification
from pathlib import Path
import json
_CATEGORY_KEYWORDS = json.loads(Path(__file__).with_name("blocker_keywords.json").read_text())


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words and bigrams."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9_\s-]", " ", text)
    words = text.split()
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i + 1]}")
    return tokens


class RiskEngine:
    """Deterministic risk heuristics; not a calibrated probability of release failure."""

    # Feature weights for risk scoring
    _WEIGHTS = {
        "criteria_pass_rate": -30.0,
        "required_criteria_pass_rate": -25.0,
        "blocker_density": 20.0,
        "critical_blocker_count": 15.0,
        "high_blocker_count": 8.0,
        "approval_rate": -10.0,
        "evidence_coverage": -10.0,
        "days_to_target_penalty": 10.0,
        "waived_criteria_ratio": 5.0,
        "unassigned_criteria_ratio": 5.0,
    }

    def extract_features(self, release_data: dict[str, Any]) -> dict[str, float]:
        """Extract numerical features from release data for risk scoring."""
        criteria = release_data.get("criteria", [])
        blockers = release_data.get("blockers", [])
        approvals = release_data.get("approvals", [])

        total_criteria = len(criteria) if criteria else 0
        passed_criteria = sum(1 for c in criteria if c.get("status") == "passed")
        required_criteria = [c for c in criteria if c.get("required")]
        required_passed = sum(1 for c in required_criteria if c.get("status") == "passed")
        with_evidence = sum(1 for c in criteria if c.get("evidence"))
        waived = sum(1 for c in criteria if c.get("status") == "waived")
        unassigned = sum(1 for c in criteria if not c.get("assigned_to"))

        open_blockers = [b for b in blockers if b.get("status") not in ("resolved", "accepted")]
        critical_blockers = sum(1 for b in open_blockers if b.get("severity") == "critical")
        high_blockers = sum(1 for b in open_blockers if b.get("severity") == "high")

        approved_count = sum(1 for a in approvals if a.get("decision") == "approved")
        total_approvals = len(approvals) if approvals else 0

        days_to_target = release_data.get("days_to_target", 30)

        return {
            "criteria_pass_rate": (passed_criteria / total_criteria) if total_criteria > 0 else 0.0,
            "required_criteria_pass_rate": (
                (required_passed / len(required_criteria)) if required_criteria else 1.0
            ),
            "blocker_density": (len(open_blockers) / total_criteria) if total_criteria > 0 else 0.0,
            "critical_blocker_count": float(critical_blockers),
            "high_blocker_count": float(high_blockers),
            "approval_rate": (approved_count / total_approvals) if total_approvals > 0 else 0.0,
            "evidence_coverage": (with_evidence / total_criteria) if total_criteria > 0 else 0.0,
            "waived_criteria_ratio": (waived / total_criteria) if total_criteria > 0 else 0.0,
            "unassigned_criteria_ratio": (unassigned / total_criteria) if total_criteria > 0 else 0.0,
            "days_to_target": float(days_to_target),
        }

    def compute_risk_score(self, features: dict[str, float]) -> float:
        """Compute deterministic risk score from features (0-100 scale)."""
        score = 50.0  # baseline

        score += self._WEIGHTS["criteria_pass_rate"] * features.get("criteria_pass_rate", 0.0)
        score += self._WEIGHTS["required_criteria_pass_rate"] * features.get(
            "required_criteria_pass_rate", 0.0
        )
        score += self._WEIGHTS["blocker_density"] * features.get("blocker_density", 0.0)
        score += self._WEIGHTS["critical_blocker_count"] * min(
            features.get("critical_blocker_count", 0.0), 5.0
        )
        score += self._WEIGHTS["high_blocker_count"] * min(
            features.get("high_blocker_count", 0.0), 5.0
        )
        score += self._WEIGHTS["approval_rate"] * features.get("approval_rate", 0.0)
        score += self._WEIGHTS["evidence_coverage"] * features.get("evidence_coverage", 0.0)

        # Sigmoid penalty for negative days-to-target
        days = features.get("days_to_target", 30.0)
        if days < 0:
            time_penalty = 1.0 / (1.0 + math.exp(0.5 * days))
            score += self._WEIGHTS["days_to_target_penalty"] * time_penalty
        elif days < 7:
            time_penalty = (7.0 - days) / 7.0 * 0.5
            score += self._WEIGHTS["days_to_target_penalty"] * time_penalty

        score += self._WEIGHTS["waived_criteria_ratio"] * features.get("waived_criteria_ratio", 0.0)
        score += self._WEIGHTS["unassigned_criteria_ratio"] * features.get(
            "unassigned_criteria_ratio", 0.0
        )

        return max(0.0, min(100.0, score))

    def classify_risk(self, score: float) -> str:
        """Classify risk level from score."""
        if score < 25:
            return "low"
        if score < 50:
            return "medium"
        if score < 75:
            return "elevated"
        return "critical"

    def classify_blocker(self, title: str, description: str) -> dict[str, Any]:
        """Classify a blocker using NLP keyword frequency analysis."""
        combined_text = f"{title} {description}"
        tokens = _tokenize(combined_text)
        token_set = set(tokens)

        category_scores: dict[str, tuple[float, list[str]]] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            matched = [kw for kw in keywords if kw in token_set]
            if not matched:
                for kw in keywords:
                    for token in tokens:
                        if kw in token and kw not in matched:
                            matched.append(kw)
            score = len(matched) / len(keywords) if keywords else 0.0
            category_scores[category] = (score, matched)

        best_category = "uncategorized"
        best_score = 0.0
        best_matched: list[str] = []
        for cat, (sc, matched) in category_scores.items():
            if sc > best_score:
                best_category = cat
                best_score = sc
                best_matched = matched

        confidence = min(1.0, best_score * 5.0) if best_score > 0 else 0.0

        return {
            "category": best_category,
            "confidence": round(confidence, 3),
            "keywords_matched": best_matched,
        }

    def detect_risk_patterns(
        self, releases_history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Analyze historical releases to find recurring risk patterns."""
        if not releases_history:
            return []

        patterns: list[dict[str, Any]] = []

        # Pattern 1: Recurring blocker categories
        blocker_categories: Counter[str] = Counter()
        for release in releases_history:
            for blocker in release.get("blockers", []):
                cat = blocker.get("category", "uncategorized")
                if cat:
                    blocker_categories[cat] += 1

        for cat, count in blocker_categories.most_common(3):
            if count >= 2:
                patterns.append({
                    "pattern": "recurring_blocker_category",
                    "category": cat,
                    "frequency": count,
                    "description": f"'{cat}' blockers appeared in {count} releases",
                    "recommendation": f"Establish proactive {cat} review gates before release",
                })

        # Pattern 2: Frequently failing criteria categories
        criteria_failures: Counter[str] = Counter()
        for release in releases_history:
            for criterion in release.get("criteria", []):
                if criterion.get("status") == "failed":
                    criteria_failures[criterion.get("category", "unknown")] += 1

        for cat, count in criteria_failures.most_common(3):
            if count >= 2:
                patterns.append({
                    "pattern": "recurring_criteria_failure",
                    "category": cat,
                    "frequency": count,
                    "description": f"'{cat}' criteria failed in {count} releases",
                    "recommendation": f"Invest in {cat} automation and earlier validation",
                })

        # Pattern 3: Risk score correlation with outcomes
        completed = [
            r for r in releases_history if r.get("status") in ("released", "cancelled")
        ]
        if len(completed) >= 2:
            released_scores = [
                r.get("risk_score", 50) for r in completed if r.get("status") == "released"
            ]
            cancelled_scores = [
                r.get("risk_score", 50) for r in completed if r.get("status") == "cancelled"
            ]
            if released_scores and cancelled_scores:
                avg_released = sum(released_scores) / len(released_scores)
                avg_cancelled = sum(cancelled_scores) / len(cancelled_scores)
                if avg_cancelled > avg_released + 10:
                    patterns.append({
                        "pattern": "risk_score_predictive",
                        "frequency": len(completed),
                        "description": (
                            f"Cancelled releases averaged risk score {avg_cancelled:.0f} "
                            f"vs {avg_released:.0f} for released"
                        ),
                        "recommendation": "Risk scores above threshold correlate with cancellation",
                    })

        # Pattern 4: Time pressure correlation
        overdue_releases = sum(
            1 for r in releases_history
            if r.get("days_to_target", 30) < 0 and r.get("status") == "cancelled"
        )
        if overdue_releases >= 2:
            patterns.append({
                "pattern": "overdue_cancellation",
                "frequency": overdue_releases,
                "description": f"{overdue_releases} overdue releases were cancelled",
                "recommendation": "Set realistic target dates or add buffer time",
            })

        return patterns

    def assess_readiness(
        self,
        release_data: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Comprehensive release readiness assessment combining all analysis."""
        features = self.extract_features(release_data)
        risk_score = self.compute_risk_score(features)
        risk_level = self.classify_risk(risk_score)

        risk_factors: list[str] = []
        if features["required_criteria_pass_rate"] < 1.0:
            pct = features["required_criteria_pass_rate"] * 100
            risk_factors.append(f"Required criteria pass rate is {pct:.0f}% (must be 100%)")
        if features["critical_blocker_count"] > 0:
            n = int(features["critical_blocker_count"])
            risk_factors.append(f"{n} critical blocker(s) remain open")
        if features["high_blocker_count"] > 0:
            n = int(features["high_blocker_count"])
            risk_factors.append(f"{n} high-severity blocker(s) remain open")
        if features["evidence_coverage"] < 0.5:
            pct = features["evidence_coverage"] * 100
            risk_factors.append(f"Evidence coverage is only {pct:.0f}%")
        if features["approval_rate"] < 0.5 and features.get("days_to_target", 30) < 7:
            risk_factors.append("Low approval rate with approaching deadline")
        if features["waived_criteria_ratio"] > 0.2:
            pct = features["waived_criteria_ratio"] * 100
            risk_factors.append(f"{pct:.0f}% of criteria were waived")
        if features["unassigned_criteria_ratio"] > 0.3:
            pct = features["unassigned_criteria_ratio"] * 100
            risk_factors.append(f"{pct:.0f}% of criteria are unassigned")
        days = features.get("days_to_target", 30)
        if days is not None and days < 0:
            risk_factors.append(f"Release is {abs(int(days))} day(s) overdue")

        recommendations: list[str] = []
        if features["required_criteria_pass_rate"] < 1.0:
            recommendations.append("Address all failing required criteria before approval")
        if features["critical_blocker_count"] > 0:
            recommendations.append("Resolve critical blockers immediately")
        if features["evidence_coverage"] < 0.8:
            recommendations.append("Collect evidence for uncovered criteria")
        if features["unassigned_criteria_ratio"] > 0.2:
            recommendations.append("Assign owners to unassigned criteria")
        if features["approval_rate"] < 0.5:
            recommendations.append("Obtain additional stakeholder approvals")

        result: dict[str, Any] = {
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "features": {k: round(v, 4) for k, v in features.items()},
            "risk_factors": risk_factors,
            "recommendations": recommendations,
            "ready_for_release": (
                risk_score < 30
                and features["critical_blocker_count"] == 0
                and features["required_criteria_pass_rate"] == 1.0
            ),
        }

        if history:
            result["patterns"] = self.detect_risk_patterns(history)

        return result


# Module-level singleton
risk_engine = RiskEngine()
