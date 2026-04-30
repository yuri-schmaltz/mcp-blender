import socket
import json

def test_command(cmd_type, params=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    try:
        s.connect(('localhost', 9876))
        payload = {"type": cmd_type, "params": params or {}}
        s.sendall(json.dumps(payload).encode('utf-8'))
        
        # Read until EOF
        res = b""
        while True:
            try:
                data = s.recv(4096)
                if not data: break
                res += data
                # Check if we have a valid JSON
                try:
                    json.loads(res.decode('utf-8'))
                    break
                except: continue
            except socket.timeout:
                break
        return json.loads(res.decode('utf-8'))
    finally:
        s.close()

print("--- TESTING SOCKET: list_tools ---")
try:
    res = test_command("list_tools")
    print("RES STATUS:", res.get("status"))
    print("TOOLS COUNT:", len(res.get("result", [])))
except Exception as e:
    print("ERROR:", e)
