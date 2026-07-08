from src.scoring import status_from_score


def test_status_thresholds() -> None:
    assert status_from_score(90) == "GREEN"
    assert status_from_score(85) == "GREEN"
    assert status_from_score(84.9) == "AMBER"
    assert status_from_score(60) == "AMBER"
    assert status_from_score(59.9) == "RED"
