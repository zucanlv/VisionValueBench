#!/usr/bin/env python3
"""Compute scores from frozen four-state counts with Python's standard library.

Usage: python scripts/score.py analysis/profiles.csv > scored.csv
       python scripts/score.py analysis/profiles.csv --check
       cat counts.csv | python scripts/score.py -

This portable helper implements the published count identities; it does not
generate images, annotate evidence, aggregate verifier votes, or bootstrap.
Undefined score/prevalence values are written as empty CSV cells. --check
validates any existing n, supported, score, and prevalence columns instead of
writing CSV. Other columns, including identifiers, are preserved.
"""

import argparse
import csv
import math
import sys


COUNTS = ("a_only", "b_only", "both", "neither")
DERIVED = ("n", "supported", "score", "prevalence")


def nonnegative_integer(value, name):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a nonnegative integer") from None
    if result < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return result


def calculate(row):
    a, b, both, neither = [nonnegative_integer(row[k], k) for k in COUNTS]
    supported = a + b + both
    n = supported + neither
    return {
        "n": n,
        "supported": supported,
        "score": (a - b) / supported if supported else None,
        "prevalence": supported / n if n else None,
    }


def check_existing(row, derived):
    for key, expected in derived.items():
        if key not in row:
            continue
        value = row[key]
        if expected is None:
            matches = value is not None and not value.strip()
        elif key in ("n", "supported"):
            matches = nonnegative_integer(value, key) == expected
        else:
            try:
                actual = float(value)
                matches = math.isfinite(actual) and abs(actual - expected) <= 1e-12
            except (TypeError, ValueError):
                matches = False
        if not matches:
            raise ValueError(f"{key} is {value!r}; expected {expected!r}")


def process(source, check):
    reader = csv.DictReader(source)
    fields = reader.fieldnames or []
    missing = [k for k in COUNTS if k not in fields]
    if missing:
        raise ValueError("Missing count columns: " + ", ".join(missing))
    if len(fields) != len(set(fields)):
        raise ValueError("Duplicate CSV column names")
    writer = None
    if not check:
        writer = csv.DictWriter(sys.stdout, fieldnames=fields + [k for k in DERIVED if k not in fields])
        writer.writeheader()
    count = 0
    for count, row in enumerate(reader, 1):
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("CSV row length does not match its header")
            derived = calculate(row)
            if check:
                check_existing(row, derived)
            else:
                row.update(derived)
                writer.writerow(row)
        except ValueError as error:
            raise ValueError(f"Row {count}: {error}") from None
    if check:
        print(f"Checked {count} rows.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", help="Input CSV path, or - for standard input")
    parser.add_argument("--check", action="store_true", help="Check existing derived columns; write no CSV")
    args = parser.parse_args()
    try:
        if args.csv_file == "-":
            process(sys.stdin, args.check)
        else:
            with open(args.csv_file, encoding="utf-8-sig", newline="") as source:
                process(source, args.check)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
