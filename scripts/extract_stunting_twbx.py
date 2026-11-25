"""
Extract the NITI team's stunting prescriptive model from their Tableau workbook into plain CSV files
(the stunting counterpart of scripts/extract_niti_twbx.py, which does the same for dropout).

    <python with tableauhyperapi> scripts/extract_stunting_twbx.py

Input : backend/app/data/niti/stunting/Prescriptive_district_view_stunting_under5_01.twbx
        downloaded from Tableau Public (karnataka.data.lake, "Prescriptive district view (children who are
        stunted under the age of 5 years)_01", published Nov 2026).
Output: backend/app/data/niti/stunting/
          factors_all_india.csv   one row per (state, district, factor): the district's value, the fitted line
                                  (M = slope, intercept), Pearson r, direction match, bucket, factor label, scaler,
                                  and the model's prediction error / confidence for the target row
          factors_karnataka.csv   the same rows, Karnataka only

The dashboard's sheets read the "stunting_dominant_model_PROVISIONAL_v2 (1)" data source -- the authors mark the
model PROVISIONAL. The workbook also carries leftover dropout extracts and an older provisional stunting extract;
those are ignored. Needs Tableau's Hyper API (`pip install tableauhyperapi`), only when a new workbook arrives.
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import zipfile

from tableauhyperapi import Connection, HyperProcess, Telemetry

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIR = os.path.join(ROOT, "backend", "app", "data", "niti", "stunting")
TWBX = os.path.join(DIR, "Prescriptive_district_view_stunting_under5_01.twbx")
# The extract behind every sheet of the "prescriptive district" dashboard (see the .twb's datasources).
EXTRACT = "Data/TableauTemp/#TableauTemp_1m7kwhq1vqi94f1gqxr881io8w76.hyper"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(TWBX) as z:
        z.extractall(tmp)
        with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
            with Connection(hp.endpoint, os.path.join(tmp, EXTRACT)) as c:
                table = c.catalog.get_table_names("Extract")[0]
                cols = [str(col.name).strip('"') for col in c.catalog.get_table_definition(table).columns]
                rows = c.execute_list_query(f"SELECT * FROM {table} ORDER BY 1, 2, 3")
    cols = [col for col in cols if col != "Map Placeholder"]
    rows = [r[: len(cols)] for r in rows]
    karnataka = [r for r in rows if str(r[0]).strip().lower() == "karnataka"]
    for name, data in (("factors_all_india.csv", rows), ("factors_karnataka.csv", karnataka)):
        with open(os.path.join(DIR, name), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows(data)
        print(f"wrote {name}: {len(data)} rows")
    print(f"columns: {cols}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
