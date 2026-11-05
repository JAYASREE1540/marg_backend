import os, subprocess, sys, time

def run_zap(target_url, html="dast_report.html", json="dast_report.json"):
    subprocess.Popen(["zap.sh","-daemon","-port","8090","-config","api.disablekey=true"])
    time.sleep(30)                       # wait for ZAP to start
    cmd = ["zap-baseline.py","-t",target_url,"-r",html,"-J",json,"-p","8090","-config","api.disablekey=true"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        print("ZAP failed:", result.stderr)
        sys.exit(result.returncode)
    print(f"ZAP complete → {html}, {json}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_zap.py <target_url>")
        sys.exit(1)
    run_zap(sys.argv[1])
