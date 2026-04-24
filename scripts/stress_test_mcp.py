import json
import socket
import time
import random
import sys
import traceback
import argparse

class MCPStressTester:
    def __init__(self, host="localhost", port=9876):
        self.host = host
        self.port = port
        self.stats = {
            "total_sent": 0,
            "success": 0,
            "failed": 0,
            "latencies": []
        }

    def send_command(self, cmd_type, params=None):
        payload = {"type": cmd_type, "params": params or {}}
        t0 = time.time()
        self.stats["total_sent"] += 1
        
        try:
            with socket.create_connection((self.host, self.port), timeout=10.0) as sock:
                sock.sendall(json.dumps(payload).encode("utf-8"))
                
                # Receive response
                buffer = b""
                while True:
                    chunk = sock.recv(16384)
                    if not chunk: break
                    buffer += chunk
                    try:
                        resp = json.loads(buffer.decode("utf-8"))
                        latency = (time.time() - t0) * 1000
                        self.stats["latencies"].append(latency)
                        if resp.get("status") == "success":
                            self.stats["success"] += 1
                        else:
                            self.stats["failed"] += 1
                        return resp
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            self.stats["failed"] += 1
            return {"status": "error", "message": str(e)}

    def run_suite(self):
        print(f"🚀 Starting Intensive Stress Test on {self.host}:{self.port}")
        print("="*60)

        # 1. Connectivity & Basic Info
        print("🔍 [TEST 1] Connectivity & Scene Discovery...")
        resp = self.send_command("get_scene_info")
        if resp.get("status") == "success":
            res = resp["result"]
            print(f"   OK: Found {len(res.get('objects', []))} objects in scene.")
        else:
            print(f"   FAIL: {resp.get('message')}")

        # 2. Rapid-Fire Primitives (Stress Test Creation)
        count = 10
        print(f"🏗️ [TEST 2] Rapid-Fire Creation ({count} cubes)...")
        for i in range(count):
            name = f"StressCube_{i}"
            loc = [random.uniform(-5, 5) for _ in range(3)]
            self.send_command("add_primitive", {"type": "cube", "name": name, "location": loc})
        print(f"   Done: {count} requests sent.")

        # 3. Mass Transformation (Performance Test)
        print("🔄 [TEST 3] Mass Transformation (Random Scale/Rotate)...")
        for i in range(count):
            name = f"StressCube_{i}"
            rot = [random.uniform(0, 360) for _ in range(3)]
            self.send_command("transform_object", {"name": name, "rotation": rot, "scale": [1.5, 0.5, 1.2]})
        print(f"   Done: {count} updates sent.")

        # 4. Mesh Integrity & Repairs
        print("🔧 [TEST 4] Mesh Engineering Tools...")
        # Add a Suzanne and check integrity
        self.send_command("add_primitive", {"type": "monkey", "name": "SuzanneTest"})
        resp = self.send_command("check_mesh_integrity", {"object_name": "SuzanneTest"})
        if resp.get("status") == "success":
            print(f"   Integrity Check OK: {resp['result'].get('message')}")
        
        # Test self-intersection resolver
        print("🩹 [TEST 5] Self-Intersection Resolver...")
        resp = self.send_command("resolve_self_intersections", {"object_name": "SuzanneTest"})
        if resp.get("status") == "success":
            print(f"   Repair OK: {resp['result'].get('message')}")

        # 5. Heavy Code Execution
        print("💻 [TEST 6] Heavy Code Execution (Bulk Property Injection)...")
        heavy_code = """
import bpy
for obj in bpy.data.objects:
    if obj.name.startswith("StressCube"):
        obj["mcp_stress_test"] = True
        obj["stress_timestamp"] = "2026-04-24"
"""
        resp = self.send_command("execute_code", {"code": heavy_code})
        if resp.get("status") == "success":
            print("   Execution OK.")
        else:
            print(f"   Execution BLOCKED or FAILED: {resp.get('message')}")

        # 6. Cleanup
        print("🧹 [TEST 7] Scene Cleanup via Code...")
        cleanup_code = """
import bpy
objs = [o for o in bpy.data.objects if o.name.startswith("StressCube") or o.name == "SuzanneTest"]
for o in objs:
    bpy.data.objects.remove(o, do_unlink=True)
"""
        self.send_command("execute_code", {"code": cleanup_code})
        print("   Cleanup Done.")

        self.print_report()

    def print_report(self):
        avg_lat = sum(self.stats["latencies"]) / len(self.stats["latencies"]) if self.stats["latencies"] else 0
        print("\n" + "="*60)
        print("📊 FINAL STRESS TEST REPORT")
        print("="*60)
        print(f"Total Commands Sent: {self.stats['total_sent']}")
        print(f"Successful:         {self.stats['success']}")
        print(f"Failed:             {self.stats['failed']}")
        print(f"Average Latency:    {avg_lat:.2f} ms")
        print(f"Reliability:        {(self.stats['success']/self.stats['total_sent'])*100:.1f}%")
        print("="*60)
        if self.stats["failed"] == 0:
            print("🏆 STATUS: EXCELLENCE ACHIEVED (v2.5.1 Robustness Verified)")
        else:
            print("⚠️ STATUS: DEGRADED PERFORMANCE DETECTED")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BlenderMCP Exhaustive Stress Tester")
    parser.add_argument("--port", type=int, default=9876, help="MCP Server Port")
    args = parser.parse_args()
    
    tester = MCPStressTester(port=args.port)
    try:
        tester.run_suite()
    except KeyboardInterrupt:
        print("\nTest aborted by user.")
    except Exception as e:
        print(f"\nCritical failure during test: {e}")
        traceback.print_exc()
