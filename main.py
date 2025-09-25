#!/usr/bin/env python3
"""
CapCut Auto Project Creator — CLI entrypoint.

Default behavior:
  If no arguments are passed, runs as:
      python main.py --config capcut_creator_config.yaml --full

Usage examples:
  python main.py --config ./capcut_creator_config.yaml --full
  python main.py --config ./capcut_creator_config.yaml --slice scan_assets --slice build_timeline --slice write_json
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Dict

from initializer import (
    Context,
    build_pipeline,
    STAGE_REGISTRY,
    StageBase,
)

# ---------------- Logging ----------------

def setup_logging(level_str: str | None, logfile: str | None, fmt: str | None):
    level_map = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        None: logging.INFO,
    }
    level = level_map.get(level_str, logging.INFO)
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if logfile:
        handlers.append(logging.FileHandler(logfile, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format=fmt or "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=handlers,
    )

# ---------------- CLI ----------------

def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="CapCut - Auto Project Creator (modular pipeline)")

    ap.add_argument("--config", help="Path to capcut_creator_config.yaml")
    ap.add_argument("--full", action="store_true", help="Run the full pipeline")
    ap.add_argument(
        "--slice",
        action="append",
        dest="slices",
        help="Run only specific stage(s). May be repeated. "
             "Valid: " + ", ".join(sorted(STAGE_REGISTRY.keys()))
    )
    ap.add_argument("--project-root", help="Override project_root from YAML")
    ap.add_argument("--fix", action="store_true", help="Enable doctor.autofix regardless of YAML")
    ap.add_argument("--verbose", default=None, help="Logging level: DEBUG|INFO|WARNING|ERROR|CRITICAL")
    ap.add_argument("--log-file", default=None, help="Write logs to this file as well")
    ap.add_argument("--log-format", default=None, help="Override logging format string")

    # Default if no args given at all
    if argv is None and len(sys.argv) == 1:
        argv = ["--config", "capcut_creator_config.yaml", "--full"]

    return ap.parse_args(argv)


def main():
    args = parse_args()

    # Temporary logging until YAML stage reconfigures if needed
    setup_logging(args.verbose, args.log_file, args.log_format)
    
    # Validate config file exists
    if not args.config:
        logging.error("No config file specified")
        sys.exit(1)
        
    config_path = Path(args.config)
    if not config_path.exists():
        logging.error("Config file not found: %s", config_path)
        sys.exit(1)

    # Build stages & empty Context
    stages, ctx = build_pipeline(config_path)

    # If slices provided, filter by those; otherwise --full
    if not args.full and not args.slices:
        raise SystemExit("Choose --full or provide one or more --slice entries.")

    selected: List[StageBase]
    if args.full:
        selected = stages
    else:
        want = set(s.lower() for s in args.slices or [])
        selected = [st for st in stages if st.name().lower() in want]
        if not selected:
            raise SystemExit("No valid stages matched your --slice filters.")

    # Run stages
    try:
        for st in selected:
            logging.info(">> Stage: %s", st.name())
            ctx = st.run(ctx, cli_overrides={
                "project_root": args.project_root,
                "doctor_autofix": args.fix,
                "verbosity": args.verbose,
                "log_file": args.log_file,
                "log_format": args.log_format,
            })

        logging.info("✓ Done. Project dir: %s", ctx.project_dir or "(not created)")
        
        # Show summary if we have diagnostics
        if ctx.diagnostics:
            issues = ctx.diagnostics.get("issues", [])
            fixes = ctx.diagnostics.get("fixes_applied", [])
            if issues:
                logging.warning("Doctor found %d issue(s)", len(issues))
            if fixes:
                logging.info("Doctor applied %d fix(es)", len(fixes))
                
    except Exception as e:
        logging.error("Pipeline failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()