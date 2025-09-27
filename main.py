# main.py
import argparse
import json
from pathlib import Path

from initializer import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="CapCut Auto Project Creator (template-driven, no hard-coded JSON)"
    )
    parser.add_argument(
        "--config",
        default="capcut_creator_config.yaml",
        help="Path to YAML config (defaults to capcut_creator_config.yaml)",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Optional explicit project name (otherwise uses name_pattern in YAML)",
    )
    args = parser.parse_args()

    summary = run_pipeline(Path(args.config), project_name=args.project_name)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
