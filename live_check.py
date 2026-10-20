import base64, getpass, json, os, socket, time
import requests

PORT = 8000
sub = input("Company subdomain [acme]: ").strip() or "acme"
email = input("Owner email: ").strip()
password = getpass.getpass("Password (type karte waqt nazar nahi aayega): ")
key = input("API key (sk_...): ").strip()
HOST = f"{sub}.localhost:{PORT}"
BASE = f"http://127.0.0.1:{PORT}"


def post(path, data, headers=None):
    h = {"Host": HOST}
    h.update(headers or {})
    return s.post(BASE + path, json=data, headers=h, timeout=30)


def read_exact(sock, n, pre):
    data = pre
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return data[:n], data[n:]


def frame(sock, pre, timeout):
    sock.settimeout(timeout)
    hdr, pre = read_exact(sock, 2, pre)
    op, ln = hdr[0] & 15, hdr[1] & 127
    if ln == 126:
        ext, pre = read_exact(sock, 2, pre)
        ln = int.from_bytes(ext, "big")
    elif ln == 127:
        ext, pre = read_exact(sock, 8, pre)
        ln = int.from_bytes(ext, "big")
    payload, pre = read_exact(sock, ln, pre)
    return op, payload, pre


def wait_total(sock, pre, want, secs):
    end = time.time() + secs
    last = None
    while time.time() < end:
        try:
            op, payload, pre = frame(sock, pre, max(1, end - time.time()))
        except (socket.timeout, EOFError, OSError):
            break
        if op == 1:
            last = json.loads(payload)
            if last.get("total_events") >= want:
                return True, last, pre
    return False, last, pre


s = requests.Session()
r = post("/api/login/", {"username": email, "password": password})
print("1. Login:", "PASS" if r.status_code == 200 else f"FAIL ({r.status_code} {r.text[:100]})")
if r.status_code != 200:
    raise SystemExit

cookie = "; ".join(f"{c.name}={c.value}" for c in s.cookies)
sock = socket.create_connection(("127.0.0.1", PORT), timeout=8)
wskey = base64.b64encode(os.urandom(16)).decode()
req = (f"GET /ws/metrics/ HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
       f"Sec-WebSocket-Key: {wskey}\r\nSec-WebSocket-Version: 13\r\nOrigin: http://{HOST}\r\nCookie: {cookie}\r\n\r\n")
sock.sendall(req.encode())
buf = b""
while b"\r\n\r\n" not in buf:
    buf += sock.recv(4096)
head, _, pre = buf.partition(b"\r\n\r\n")
status = int(head.split(b" ")[1])
print("2. WebSocket connect:", "PASS" if status == 101 else f"FAIL (status {status})")
if status != 101:
    raise SystemExit

op, payload, pre = frame(sock, pre, 10)
total0 = json.loads(payload)["total_events"]
print(f"   Shuru ka total events: {total0}")

auth = {"Authorization": f"Api-Key {key}"}
r = post("/api/ingest/", {"name": "signup", "value": 1}, auth)
print("3. Ek event bheja:", r.status_code, r.text[:60])
ok, last, pre = wait_total(sock, pre, total0 + 1, 15)
print("   Dashboard par bina refresh badha:", "PASS" if ok else f"FAIL (last={last})")

for _ in range(20):
    post("/api/ingest/", {"name": "purchase", "value": 5}, auth)
print("4. 20 events tezi se bheje")
ok, last, pre = wait_total(sock, pre, total0 + 21, 20)
print("   20 events ke baad live update aaya:", "PASS" if ok else f"FAIL (last total={last and last.get('total_events')})")
sock.close()