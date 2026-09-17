"""Clone student repositories listed in an Excel registration workbook."""

from __future__ import annotations

import argparse
import csv
import logging
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


REQUIRED_COLUMNS = {"Email", "Git Repository URL"}


def load_excel(excel_path: Path) -> pd.DataFrame:
    """Read the registration workbook and verify its required columns."""
    dataframe = pd.read_excel(excel_path)
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Workbook is missing required column(s): {missing}")
    return dataframe


def get_netid(email: str) -> str:
    """Extract the NetID portion of an email address."""
    return email.strip().split("@", maxsplit=1)[0]


def convert_to_ssh(repository_url: str) -> str:
    """Convert an HTTPS GitHub or GitLab repository page URL to an SSH URL."""
    parsed_url = urlparse(repository_url.strip())
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("Repository URL must be a valid HTTP(S) URL")

    repository_path = parsed_url.path.strip("/")
    if not repository_path:
        raise ValueError("Repository URL does not include a repository path")

    if not repository_path.endswith(".git"):
        repository_path = f"{repository_path}.git"

    return f"git@{parsed_url.netloc}:{repository_path}"


def clone_repo(ssh_url: str, destination: Path) -> None:
    """Clone one repository into *destination* using local SSH credentials."""
    subprocess.run(
        ["git", "clone", ssh_url, str(destination)],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> None:
    """Load registrations, clone repositories, and record any failures."""
    parser = argparse.ArgumentParser(
        description="Clone student Git repositories from an Excel workbook."
    )
    parser.add_argument(
        "excel_path",
        nargs="?",
        type=Path,
        default=Path("CMSE Project Registration.xlsx"),
        help="Path to the registration workbook.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    repos_directory = Path("repos")
    repos_directory.mkdir(exist_ok=True)
    failures: list[dict[str, str]] = []

    try:
        registrations = load_excel(args.excel_path)
    except Exception as error:
        logging.error("Could not load workbook %s: %s", args.excel_path, error)
        return

    for _, registration in registrations.iterrows():
        email = str(registration["Email"]).strip()
        repository_url = str(registration["Git Repository URL"]).strip()
        netid = get_netid(email)
        destination = repos_directory / netid

        try:
            if not email or email.lower() == "nan":
                raise ValueError("Email is missing")
            if not repository_url or repository_url.lower() == "nan":
                raise ValueError("Git Repository URL is missing")
            if destination.exists():
                logging.info("Skipping %s; %s already exists", netid, destination)
                continue

            ssh_url = convert_to_ssh(repository_url)
            clone_repo(ssh_url, destination)
            logging.info("Cloned %s into %s", netid, destination)
        except Exception as error:
            error_message = str(error)
            if isinstance(error, subprocess.CalledProcessError):
                error_message = error.stderr.strip() or error_message
            logging.error("Failed to clone %s: %s", netid or email, error_message)
            failures.append(
                {
                    "NetID": netid,
                    "Email": email,
                    "Repository URL": repository_url,
                    "Error Message": error_message,
                }
            )

    if failures:
        failures_path = Path("clone_failures.csv")
        with failures_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=failures[0].keys())
            writer.writeheader()
            writer.writerows(failures)
        logging.info("Wrote %d failure(s) to %s", len(failures), failures_path)


if __name__ == "__main__":
    main()