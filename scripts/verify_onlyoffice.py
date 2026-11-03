"""Exercise the application converter against a local ONLYOFFICE Docs 10 service."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--env-file", type=Path, help="Optional ONLYOFFICE_JWT_SECRET or JWT_SECRET file")
    parser.add_argument("--url", help="Override ONLYOFFICE_URL")
    args = parser.parse_args()
    if args.env_file:
        values = dict(
            line.split("=", 1)
            for line in args.env_file.read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        os.environ["ONLYOFFICE_JWT_SECRET"] = values.get(
            "ONLYOFFICE_JWT_SECRET", values.get("JWT_SECRET", "")
        )
    if args.url:
        os.environ["ONLYOFFICE_URL"] = args.url
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.pdf_converter import convert_pdf

    source = args.source.read_bytes()
    started = time.monotonic()
    pdf = convert_pdf(source)
    seconds = round(time.monotonic() - started, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(pdf)
    evidence = {
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "seconds": seconds,
        "bytes": len(pdf),
        "converter": "app.pdf_converter.convert_pdf",
    }
    args.output.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
