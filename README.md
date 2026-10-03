# GitGrab

Clone student Git repositories listed in an Excel registration workbook.

## Requirements

- Python 3
- `pandas` and an Excel reader such as `openpyxl`
- Git and SSH access to the listed repositories

Install the Python dependencies:

```sh
python3 -m pip install pandas openpyxl
```

## Usage

The workbook must contain an `Email` column and exactly one column with `URL`
in its name, such as `Git Repository URL`. From the repository root, run:

```sh
python3 clone_repositories.py "CMSE Project Registration.xlsx"
```

To use the default workbook name (`CMSE Project Registration.xlsx`), omit the
argument:

```sh
python3 clone_repositories.py
```

Repositories are cloned into `repos/<NetID>`. Any failed clones are recorded
in `clone_failures.csv`.