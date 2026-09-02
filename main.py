"""Safe Vanguard entry point.

The audited Oracle scanner is retained as research code, but it is not a trading
entry point. Production execution must use the explicit Vanguard pipeline and a
paper/demo broker until all release gates are satisfied.
"""
from vanguard.demo_validation import run as run_demo


def main() -> None:
    print("Delphi Vanguard reliability build")
    print("Live trading is disabled. Running deterministic paper validation...")
    print(f"DEMO VALIDATION: {run_demo()}")


if __name__ == "__main__":
    main()
