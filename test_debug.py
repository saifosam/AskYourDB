"""Test script: starts Flask server, sends a query, captures ALL debug output."""
import subprocess
import time
import urllib.request
import json
import sys
import os
import signal

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Start the Flask server
print("=" * 60)
print("STARTING FLASK SERVER...")
print("=" * 60)

proc = subprocess.Popen(
    [sys.executable, "-u", "app.py"],  # -u for unbuffered output
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

# Wait for server to start
time.sleep(5)

# Read any initial output
initial_output = ""
while True:
    import select
    import socket
    
    try:
        # Check if stdout has data (non-blocking)
        proc.stdout.flush()
        break
    except:
        break

# Try to read available output (non-blocking approach)
import threading
output_lines = []

def reader():
    for line in proc.stdout:
        output_lines.append(line)

t = threading.Thread(target=reader, daemon=True)
t.start()

time.sleep(1)  # Let any initial output be captured

# Check if server is running
try:
    response = urllib.request.urlopen("http://127.0.0.1:5005/", timeout=5)
    print("\n[CLIENT] Server is running!")
except Exception as e:
    print(f"\n[CLIENT] Server might not be ready: {e}")
    # Try again after a delay
    time.sleep(3)

# Send test query
print("\n" + "=" * 60)
print("SENDING TEST QUERY: 'show me all customers from Germany'")
print("=" * 60)

try:
    req = urllib.request.Request(
        "http://127.0.0.1:5005/query",
        data=json.dumps({"question": "show me all customers from Germany"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    response = urllib.request.urlopen(req, timeout=60)
    result = json.loads(response.read().decode())
    print(f"\n[CLIENT] Query response:")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"\n[CLIENT] Query error: {e}")

# Wait a moment for any final output
time.sleep(2)

# Print all captured server output
print("\n" + "=" * 60)
print("FULL SERVER OUTPUT (stdout+stderr):")
print("=" * 60)
for line in output_lines:
    print(line, end="")

# Stop the server
print("\n" + "=" * 60)
print("STOPPING SERVER")
print("=" * 60)
proc.terminate()
proc.wait(timeout=5)

print("\nDone!")
