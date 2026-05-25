import urllib.request
import json
import time

def init():
    print("Waiting for media indexer backend to be ready...")
    for _ in range(30):
        try:
            req = urllib.request.Request("http://localhost:8000/health")
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(2)
    else:
        print("Backend did not start in time.")
        return

    print("Adding generated source...")
    data = json.dumps({"name": "Generated Media", "type": "mounted_fs", "root_path": "/data/sources/generated"}).encode("utf-8")
    req = urllib.request.Request("http://localhost:8000/sources", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read())
            source_id = res["id"]
            print(f"Added source with ID {source_id}. Triggering scan...")
            
            # Trigger scan
            req = urllib.request.Request(f"http://localhost:8000/sources/{source_id}/scan", data=b'', method="POST")
            urllib.request.urlopen(req)
            print("Scan triggered! The worker is now indexing your generated images.")
    except Exception as e:
        print(f"Failed to add source: {e}")

if __name__ == "__main__":
    init()
