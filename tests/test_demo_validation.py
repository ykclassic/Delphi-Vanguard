from vanguard.demo_validation import run


def test_end_to_end_demo_validation():
    assert run() == "POSITION_OPEN"
