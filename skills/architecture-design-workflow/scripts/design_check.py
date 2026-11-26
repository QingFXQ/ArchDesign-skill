"""Resolve shell geometry, validate a room program, or inspect site geometry."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["shell", "layout", "site"])
    parser.add_argument("input", type=Path)
    parser.add_argument("--mode", choices=["explore", "accept"], default="explore")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.report and args.input.resolve() == args.report.resolve():
            raise ValueError("Report path must differ from the input")
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if data.get("schema") != 1 or data.get("units") != "m":
            raise ValueError("Expected schema 1 with units set to m")
        if args.command == "site":
            from design_site import earthwork, routes
            if "earthwork" not in data and "paths" not in data:
                raise ValueError("Provide earthwork, paths, or both")
            result = {}
            if "earthwork" in data:
                result["earthwork"] = earthwork(data["earthwork"])
            if "paths" in data:
                result["paths"] = routes(data["paths"])
            result["passed"] = result.get("paths", {}).get("passed", True)
        else:
            try:
                from design_geometry import evaluate, shell_output
            except ImportError as exc:
                raise ValueError("Shell and layout checks require Shapely >= 2.1") from exc
            result = shell_output(data) if args.command == "shell" else evaluate(data, args.mode)
        output = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
        if args.report:
            args.report.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
        return 0 if result.get("passed", True) else 2
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        print(f"{args.command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
