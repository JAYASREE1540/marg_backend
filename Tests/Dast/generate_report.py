import json
import os
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

def _flatten_alert(alert: dict) -> dict:
    """
    Convert a single ZAP alert dict into a flat row that matches the
    spreadsheet layout you requested.
    """
    return {
        "Test ID": alert.get("alertRef", ""),
        "Category": "DAST Security",
        "Test Name": alert.get("alert", ""),
        "Objective": f"Detect {alert.get('alert', '')}",
        "Preconditions": "Application reachable, ZAP daemon running",
        "Steps": f"ZAP scanned {alert.get('url','')}",
        "Expected Result": "No high‑severity findings",
        "Actual Result": alert.get("alert", ""),
        "Status": "FAIL" if alert.get("risk") in ("High", "Medium") else "PASS",
        "Severity": alert.get("risk", ""),
        "Priority": alert.get("confidence", ""),
        "Execution Time": "",  # not applicable for static scan
        "Remarks": alert.get("description", ""),
        "Automation Status": "Automated",
    }

def generate_excel_from_zap(json_path: str, excel_path: str) -> None:
    """
    Reads the ZAP JSON report (produced by `zap-baseline.py -J …`) and writes
    an Excel file with two sheets:

    * SUMMARY – counts of PASS/FAIL per severity
    * TEST RESULTS – one row per alert (flattened as above)
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    alerts = data.get("site", [{}])[0].get("alerts", [])
    rows = [_flatten_alert(a) for a in alerts]

    # ------------------------------------------------------------------
    # Create Excel workbook
    # ------------------------------------------------------------------
    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "SUMMARY"

    # Simple summary statistics
    total = len(rows)
    passes = sum(1 for r in rows if r["Status"] == "PASS")
    fails = total - passes

    ws_summary.append(["Total Tests", total])
    ws_summary.append(["Passed", passes])
    ws_summary.append(["Failed", fails])
    ws_summary.append(["Pass Percentage", f"{(passes/total*100):.2f}%" if total else "0%"])

    # ------------------------------------------------------------------
    # Detailed test‑result sheet
    # ------------------------------------------------------------------
    ws_detail = wb.create_sheet(title="TEST RESULTS")
    if rows:
        # Write header
        ws_detail.append(list(rows[0].keys()))
        # Write data rows
        for r in rows:
            ws_detail.append(list(r.values()))
    else:
        ws_detail.append(["No alerts found – the scan reported a clean result."])

    # Save the workbook
    Path(excel_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(excel_path)
    print(f"✅ Excel report written to {excel_path}")

if __name__ == "__main__":
    # Example usage from the CI job:
    #   python generate_report.py dast_report.json dast_report.xlsx
    if len(sys.argv) != 3:
        print("Usage: python generate_report.py <zap_json_report> <excel_output>")
        sys.exit(1)

    json_file = sys.argv[1]
    excel_file = sys.argv[2]

    if not os.path.exists(json_file):
        print(f"❌ JSON report not found: {json_file}")
        sys.exit(1)

    generate_excel_from_zap(json_file, excel_file)
