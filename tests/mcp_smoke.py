"""Start tidy-server (exe or .py) like Claude does and check it lists its tools. Usage: mcp_smoke.py <exe or .py>"""
import json, subprocess, sys

target = sys.argv[1]
cmd = [sys.executable, target] if target.endswith(".py") else [target]
msgs = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
p.stdin.write(json.dumps(msgs[0]) + "\n"); p.stdin.flush()
init = json.loads(p.stdout.readline())
p.stdin.write(json.dumps(msgs[1]) + "\n" + json.dumps(msgs[2]) + "\n"); p.stdin.flush()
tools = json.loads(p.stdout.readline())
p.kill()
names = [t["name"] for t in tools["result"]["tools"]]
print(init["result"]["serverInfo"], len(names), "tools:", ", ".join(names))
if len(names) < 15 or "scan_folder" not in names:
    sys.exit("tool list incomplete")
