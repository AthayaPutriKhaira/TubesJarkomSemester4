import socket
import threading
import datetime
import os

# ─── KONFIGURASI ───────────────────────────────────────────
PROXY_HOST = '0.0.0.0'
PROXY_PORT = 8888
SERVER_HOST = '10.88.103.209'   # Ganti dengan IP Web Server jika beda mesin
SERVER_PORT = 8000
BUFFER_SIZE = 4096
TIMEOUT     = 10             # detik

# ─── CACHE (in-memory, thread-safe) ────────────────────────
cache = {}
cache_lock = threading.Lock()

# ─── HELPER: LOG ───────────────────────────────────────────
def log(tag, msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{ts}] [{tag}] {msg}")

# ─── PARSE PATH DARI REQUEST HTTP ──────────────────────────
def parse_request(raw_bytes):
    try:
        header_section = raw_bytes.split(b'\r\n\r\n')[0].decode('utf-8', errors='replace')
        lines = header_section.split('\r\n')
        request_line = lines[0]
        parts = request_line.split(' ')
        method = parts[0]
        path   = parts[1] if len(parts) > 1 else '/'
        return method, path, header_section
    except Exception as e:
        return None, None, None

# ─── FORWARD KE WEB SERVER ─────────────────────────────────
def forward_to_server(raw_request):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((SERVER_HOST, SERVER_PORT))
        sock.sendall(raw_request)

        response = b''
        while True:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk
        sock.close()
        return response
    except socket.timeout:
        log("FORWARD", "Timeout koneksi ke Web Server → 504")
        return b"HTTP/1.1 504 Gateway Timeout\r\nContent-Length: 22\r\n\r\n504 Gateway Timeout"
    except Exception as e:
        log("FORWARD", f"Error forward: {e} → 502")
        return b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 15\r\n\r\n502 Bad Gateway"

# ─── HANDLE CLIENT ─────────────────────────────────────────
def handle_client(conn, addr):
    thread_name = threading.current_thread().name
    log("PROXY", f"Koneksi dari {addr} [{thread_name}]")
    try:
        raw = b''
        conn.settimeout(TIMEOUT)
        while b'\r\n\r\n' not in raw:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            raw += chunk

        if not raw:
            conn.close()
            return

        method, path, headers = parse_request(raw)
        if method is None:
            conn.close()
            return

        client_ip = addr[0]
        log("PROXY", f"{client_ip} → {method} {path}")

        # ── CEK CACHE ──────────────────────────────────────
        with cache_lock:
            if path in cache:
                log("CACHE", f"HIT: {path} → langsung kirim ke {client_ip}")
                conn.sendall(cache[path])
                log("PROXY", f"Response cache dikirim ke {client_ip}")
                conn.close()
                return

        # ── CACHE MISS: FORWARD KE SERVER ──────────────────
        log("CACHE", f"MISS: {path} → forward ke Web Server")
        t_forward_start = datetime.datetime.now()

        # FIX UNTUK BROWSER: Paksa header Connection menjadi close
        # Agar web server segera memutus koneksi setelah mengirim file.
        # Jika browser mengirim 'keep-alive', recv() proxy akan nyangkut (blocking)
        raw = raw.replace(b'keep-alive', b'close')
        raw = raw.replace(b'Keep-Alive', b'close')

        response = forward_to_server(raw)

        t_forward_end = datetime.datetime.now()
        latency_ms = (t_forward_end - t_forward_start).total_seconds() * 1000
        log("PROXY", f"Response dari server ({len(response)} bytes, {latency_ms:.1f}ms)")

        # Simpan ke cache hanya jika response valid (200 OK)
        if response.startswith(b'HTTP/1.1 200'):
            with cache_lock:
                cache[path] = response
            log("CACHE", f"STORED: {path} ({len(response)} bytes)")

        conn.sendall(response)
        log("PROXY", f"Response diteruskan ke {client_ip}")

    except socket.timeout:
        log("PROXY", f"Timeout membaca request dari {addr}")
    except Exception as e:
        log("PROXY", f"Error menangani {addr}: {e}")
    finally:
        conn.close()

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
    log("DEBUG", f"Proxy listen di {PROXY_HOST}:{PROXY_PORT}")
    log("DEBUG", f"Forward target: {SERVER_HOST}:{SERVER_PORT}")
    log("DEBUG", "=" * 50)

def test_connection_to_server():
    log("DEBUG", f"Testing koneksi ke Web Server {SERVER_HOST}:{SERVER_PORT}...")
    try:
        test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test.settimeout(3)
        test.connect((SERVER_HOST, SERVER_PORT))
        test.close()
        log("DEBUG", f"BERHASIL terhubung ke Web Server {SERVER_HOST}:{SERVER_PORT}")
        return True
    except socket.timeout:
        log("DEBUG", f"GAGAL - Timeout koneksi ke {SERVER_HOST}:{SERVER_PORT}")
        log("DEBUG", "Pastikan webserver.py sudah jalan di Laptop A")
        return False
    except ConnectionRefusedError:
        log("DEBUG", f"GAGAL - Koneksi ditolak oleh {SERVER_HOST}:{SERVER_PORT}")
        log("DEBUG", "Pastikan webserver.py sudah jalan dan firewall tidak memblokir")
        return False
    except OSError as e:
        log("DEBUG", f"GAGAL - {e}")
        log("DEBUG", "Cek apakah IP Web Server benar dan satu jaringan")
        return False

if __name__ == '__main__':
    debug_network_info()
    test_connection_to_server()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((PROXY_HOST, PROXY_PORT))
    server.listen(20)

    log("PROXY", f"Listening on port {PROXY_PORT}, multithreading aktif")
    log("PROXY", f"Forward target: {SERVER_HOST}:{SERVER_PORT}")

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
            log("PROXY", f"Thread spawned: {t.name} untuk {addr}")
    except KeyboardInterrupt:
        log("PROXY", "Proxy dihentikan.")
    finally:
        server.close()