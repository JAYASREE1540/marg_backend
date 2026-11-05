import os, pandas as pd

def bundle(root):
    # locate the four Excel files produced by the jobs
    excel_files = []
    for sub in ("selenium", "appium", "load", "dast"):
        for f in os.listdir(os.path.join(root, sub)):
            if f.endswith(".xlsx"):
                excel_files.append(os.path.join(root, sub, f))
    # very simple concatenation for demo purposes
    writer = pd.ExcelWriter(os.path.join(root, "FINAL_TEST_SUMMARY.xlsx"), engine="openpyxl")
    for xf in excel_files:
        df = pd.read_excel(xf, sheet_name=None)   # read all sheets
        for name, sheet in df.items():
            sheet.to_excel(writer, sheet_name=f"{os.path.basename(xf)}_{name}", index=False)
    writer.save()
    print("Bundled report created at:", os.path.abspath(writer.path))

if __name__ == "__main__":
    bundle("reports")
