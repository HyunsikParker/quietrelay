import quietrelay


def test_package_root_exposes_only_privacy_preserving_entry_points() -> None:
    assert quietrelay.__all__ == ["authoritative_result", "plan_payload", "run_local_plan"]
    assert not hasattr(quietrelay, "plan_day")
    assert not hasattr(quietrelay, "CommunityRequest")
