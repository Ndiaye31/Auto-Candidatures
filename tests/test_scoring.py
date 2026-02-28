from __future__ import annotations

from pathlib import Path

from app.services.scoring import load_profile, rank_jobs, score_job


def test_load_profile_reads_yaml_fixture() -> None:
    profile = load_profile(Path("tests/fixtures/profile.yaml"))

    assert profile["preferences"]["remote"] == "preferred"
    assert profile["preferences"]["seniority"] == "mid"
    assert len(profile["keywords"]) == 3


def test_score_job_returns_structured_explanations() -> None:
    profile = load_profile(Path("tests/fixtures/profile.yaml"))
    description = (
        "Remote mid backend engineer role using Python, FastAPI and PostgreSQL. "
        "You will build APIs and async services."
    )

    result = score_job(description, profile)

    assert 0 <= result.score <= 100
    assert result.score > 70
    assert result.reasons
    assert any(reason.category == "keyword" for reason in result.reasons)
    assert any(reason.category == "bonus" for reason in result.reasons)
    assert all(reason.label for reason in result.reasons)
    assert all(reason.evidence for reason in result.reasons)


def test_rank_jobs_orders_three_offers_with_explanations() -> None:
    ranked = rank_jobs(
        [
            {
                "title": "Backend Python",
                "description": (
                    "Remote mid backend engineer using Python, FastAPI, PostgreSQL "
                    "and Docker."
                ),
            },
            {
                "title": "Frontend Onsite",
                "description": (
                    "On-site junior frontend developer focused on React and CSS."
                ),
            },
            {
                "title": "Platform Senior Hybrid",
                "description": (
                    "Hybrid senior platform engineer using Python, Kubernetes, AWS "
                    "and PostgreSQL."
                ),
            },
        ],
        Path("tests/fixtures/profile.yaml"),
    )

    assert [job.title for job in ranked] == [
        "Backend Python",
        "Platform Senior Hybrid",
        "Frontend Onsite",
    ]
    assert ranked[0].score > ranked[1].score > ranked[2].score
    assert any(reason.label == "Remote preferred" for reason in ranked[0].reasons)
    assert any(reason.label == "Seniority too high" for reason in ranked[1].reasons)
    assert any(reason.label == "Onsite role" for reason in ranked[2].reasons)
