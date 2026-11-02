"""
Extract the NITI team's prescriptive model from their Tableau workbook into plain CSV files.

    <python with tableauhyperapi> scripts/extract_niti_twbx.py

Input : backend/app/data/niti/prescriptive/India_Navigation_Dashboard_v14_District_view_677.twbx
Output: backend/app/data/niti/prescriptive/
          factors_all_india.csv     one row per (state, district, factor): the district's value for the factor and the
                                    fitted line for it (M = slope, intercept), Pearson r, direction match, bucket
          dropout_2023_24.csv       district secondary dropout rate as used in the workbook (UDISE 2023-24)
          dropout_2024_25.csv       district secondary dropout rate, 2024-25 file in the workbook

The workbook stores its data in Tableau .hyper extracts, so this needs Tableau's Hyper API
(`pip install tableauhyperapi`, kept out of backend/requirements.txt because it is only needed when a new workbook
arrives). Everything downstream (scripts/export_niti_prescriptive.py) reads the CSVs, not the workbook.
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import zipfile

from tableauhyperapi import Connection, HyperProcess, Telemetry

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIR = os.path.join(ROOT, "backend", "app", "data", "niti", "prescriptive")
TWBX = os.path.join(DIR, "India_Navigation_Dashboard_v14_District_view_677.twbx")

# (path inside the .twbx, output file, columns to keep)
EXTRACTS = [
    ("Data/India_Navigation_Dashboard_v14_District_view_677 1.twb files/Sheet1 (RUN00677_ALL_INDIA_PIVOT-PRIMARY) (2).hyper",
     "factors_all_india.csv"),
    ("Data/India_Navigation_Dashboard_v13_District_view_651.twb Files/federated 2.hyper", "dropout_2023_24.csv"),
    ("Data/India_Navigation_Dashboard_v14_District_view_677.twb Files/1 (635_2024-25_districts_dropoutrate).hyper",
     "dropout_2024_25.csv"),
]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(TWBX) as z:
        z.extractall(tmp)
        with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
            for inner, out in EXTRACTS:
                with Connection(hp.endpoint, os.path.join(tmp, inner)) as c:
                    table = c.catalog.get_table_names("Extract")[0]
                    cols = [str(col.name).strip('"') for col in c.catalog.get_table_definition(table).columns]
                    rows = c.execute_list_query(f"SELECT * FROM {table} ORDER BY 1, 2")
                with open(os.path.join(DIR, out), "w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(cols)
                    w.writerows(rows)
                print(f"wrote {out}: {len(rows)} rows, columns {cols}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
