import quietrelay
from quietrelay.rank1_candidate_v2 import run_rank1_plan_v2
from quietrelay.web import run_local_plan as web_run_local_plan


def test_package_root_exposes_only_privacy_preserving_entry_points() -> None:
    assert quietrelay.__all__ == ["authoritative_result", "plan_payload", "run_local_plan"]
    assert not hasattr(quietrelay, "plan_day")
    assert not hasattr(quietrelay, "CommunityRequest")
    assert quietrelay.run_local_plan is run_rank1_plan_v2
    assert web_run_local_plan is run_rank1_plan_v2
