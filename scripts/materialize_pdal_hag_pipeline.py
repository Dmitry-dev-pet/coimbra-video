from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--template", default="config/pdal_hag_tile.json")
    parser.add_argument("--write", default="bridge_output_009c/current-pdal-pipeline.json")
    args = parser.parse_args()

    pipeline = json.loads(Path(args.template).read_text())
    pipeline["pipeline"][0]["filename"] = args.input
    pipeline["pipeline"][-1]["filename"] = args.output
    path = Path(args.write)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pipeline, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
