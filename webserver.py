import socket
import threading
import os
import datetime

# ─── KONFIGURASI ───────────────────────────────────────────
TCP_HOST = '0.0.0.0'
TCP_PORT = 8000
UDP_PORT = 9000
BUFFER_SIZE = 4096
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── HELPER: LOG ───────────────────────────────────────────
def log(tag, msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{ts}] [{tag}] {msg}")

# ─── MIME TYPE DETECTION ───────────────────────────────────
def get_content_type(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    mime_map = {
        '.html': 'text/html; charset=utf-8',
        '.css':  'text/css; charset=utf-8',
        '.js':   'application/javascript; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.png':  'image/png',
        '.jpg':  'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif':  'image/gif',
        '.svg':  'image/svg+xml',
        '.ico':  'image/x-icon',
        '.woff': 'font/woff',
        '.woff2':'font/woff2',
        '.ttf':  'font/ttf',
        '.txt':  'text/plain; charset=utf-8',
        '.pdf':  'application/pdf',
    }
    return mime_map.get(ext, 'application/octet-stream')

# ─── HTTP RESPONSE BUILDER ─────────────────────────────────
def build_response(status_code, body, content_type='text/html; charset=utf-8'):
    status_map = {
        200: 'OK',
        404: 'Not Found',
        500: 'Internal Server Error',
    }
    reason = status_map.get(status_code, 'Unknown')
    body_bytes = body.encode('utf-8') if isinstance(body, str) else body
    response = (
        f"HTTP/1.1 {status_code} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode('utf-8') + body_bytes
    return response

# ─── HANDLE TCP CLIENT ─────────────────────────────────────
def handle_tcp_client(conn, addr):
    thread_name = threading.current_thread().name
    log("TCP", f"Koneksi dari {addr} [{thread_name}]")
    try:
        raw = b''
        while b'\r\n\r\n' not in raw:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            raw += chunk

        if not raw:
            conn.close()
            return

        # Parse request line
        try:
            header_section = raw.split(b'\r\n\r\n')[0].decode('utf-8', errors='replace')
            request_line = header_section.split('\r\n')[0]
            parts = request_line.split(' ')
            method = parts[0]
            path = parts[1] if len(parts) > 1 else '/'
        except Exception as e:
            log("TCP", f"Gagal parse request: {e}")
            conn.sendall(build_response(500, "<h1>500 Internal Server Error</h1>"))
            conn.close()
            return

        log("TCP", f"{addr} → {method} {path}")

        # Serve file
        if path == '/':
            path = '/index.html'

        filepath = os.path.join(BASE_DIR, path.lstrip('/'))
        filepath = os.path.normpath(filepath)

        # Security: pastikan file di dalam BASE_DIR
        if not filepath.startswith(BASE_DIR):
            response = build_response(403, "<h1>403 Forbidden</h1>")
            conn.sendall(response)
            log("TCP", f"403 Forbidden: {path}")
        elif os.path.isfile(filepath):
            with open(filepath, 'rb') as f:
                content = f.read()
            response = build_response(200, content, get_content_type(filepath))
            conn.sendall(response)
            log("TCP", f"200 OK: {path} ({len(content)} bytes) → {addr}")
        else:
            body = f"<h1>404 Not Found</h1><p>File <code>{path}</code> tidak ditemukan.</p>"
            response = build_response(404, body)
            conn.sendall(response)
            log("TCP", f"404 Not Found: {path} → {addr}")

    except Exception as e:
        log("TCP", f"Error menangani {addr}: {e}")
        try:
            conn.sendall(build_response(500, "<h1>500 Internal Server Error</h1>"))
        except:
            pass
    finally:
        conn.close()

# ─── TCP SERVER ────────────────────────────────────────────
def start_tcp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((TCP_HOST, TCP_PORT))
    server.listen(10)
    log("TCP-SERVER", f"Listening on port {TCP_PORT}...")

    while True:
        conn, addr = server.accept()
        t = threading.Thread(target=handle_tcp_client, args=(conn, addr), daemon=True)
        t.start()
        log("TCP-SERVER", f"Thread spawned: {t.name} untuk {addr}")

# ─── UDP SERVER (QoS Echo) ─────────────────────────────────
def start_udp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((TCP_HOST, UDP_PORT))
    log("UDP-SERVER", f"Listening on port {UDP_PORT}...")

    while True:
        try:
            data, addr = server.recvfrom(BUFFER_SIZE)
            # Echo balik payload tanpa modifikasi
            server.sendto(data, addr)
            log("UDP-ECHO", f"Echo {len(data)} bytes → {addr} | payload: {data.decode('utf-8', errors='replace').strip()}")
        except Exception as e:
            log("UDP-ECHO", f"Error: {e}")

# ─── MAIN ──────────────────────────────────────────────────
def debug_network_info():
    log("DEBUG", "=" * 50)
    log("DEBUG", "NETWORK INTERFACE INFO")
    log("DEBUG", "=" * 50)
    hostname = socket.gethostname()
    log("DEBUG", f"Hostname: {hostname}")
    try:
        local_ip = socket.gethostbyname(hostname)
        log("DEBUG", f"IP (gethostbyname): {local_ip}")
    except:
        log("DEBUG", "Tidak bisa resolve hostname")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        real_ip = s.getsockname()[0]
        s.close()
        log("DEBUG", f"IP (aktif/WiFi): {real_ip}")
    except:
        log("DEBUG", "Tidak bisa deteksi IP aktif")
    log("DEBUG", f"TCP akan listen di {TCP_HOST}:{TCP_PORT}")
    log("DEBUG", f"UDP akan listen di {TCP_HOST}:{UDP_PORT}")
    log("DEBUG", f"Base directory: {BASE_DIR}")
    files = [f for f in os.listdir(BASE_DIR) if f.endswith(('.html', '.css', '.js', '.json'))]
    log("DEBUG", f"Web files ditemukan: {files if files else '(kosong)'}")
    log("DEBUG", "=" * 50)

def test_ports():
    for port, proto in [(TCP_PORT, "TCP"), (UDP_PORT, "UDP")]:
        try:
            test = socket.socket(socket.AF_INET, socket.SOCK_STREAM if proto == "TCP" else socket.SOCK_DGRAM)
            test.bind((TCP_HOST, port))
            test.close()
            log("DEBUG", f"Port {port} ({proto}) TERSEDIA")
        except OSError as e:
            log("DEBUG", f"Port {port} ({proto}) SUDAH DIPAKAI - {e}")
            log("DEBUG", f"Matikan proses lain yang pakai port {port} atau ganti port")

if __name__ == '__main__':
    log("WEBSERVER", f"Starting Web Server (TCP:{TCP_PORT}, UDP:{UDP_PORT})")
    debug_network_info()
    test_ports()

    # Buat index.html default kalau belum ada
    default_html = os.path.join(BASE_DIR, 'index.html')
    if not os.path.isfile(default_html):
        with open(default_html, 'w') as f:
            f.write("""<!DOCTYPE html>
<html>
<head><title>Web Server Jarkom</title></head>
<body>
<h1>Selamat Datang di Web Server!</h1>
<p>Tugas Besar Jaringan Komputer - Client Proxy Server</p>
</body>
</html>""")
        log("WEBSERVER", "index.html default dibuat.")

    t_tcp = threading.Thread(target=start_tcp_server, daemon=True)
    t_udp = threading.Thread(target=start_udp_server, daemon=True)

    t_tcp.start()
    t_udp.start()

    log("WEBSERVER", "Server running on port 8000 (TCP) / 9000 (UDP), thread pool siap.")

    try:
        t_tcp.join()
    except KeyboardInterrupt:
        log("WEBSERVER", "Server dihentikan.")