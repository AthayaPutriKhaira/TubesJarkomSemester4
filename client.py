import socket
import time
import struct
import sys
import json
import argparse # Tambahan modul untuk membaca argumen terminal

PROXY_HOST = "10.88.103.224"
PROXY_PORT = 8888

WEBSERVER_HOST = "10.88.103.209"
UDP_PORT = 9000

NUM_PINGS = 50
PING_TIMEOUT = 2


def http_get(path="/"):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
        
    try:
        t_start = time.time()
        sock.connect((PROXY_HOST, PROXY_PORT))
        t_connect = time.time()

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {PROXY_HOST}:{PROXY_PORT}\r\n"
            f"Connection: close\r\n"
            f"Accept: */*\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode())
        t_sent = time.time()

        response = b""
        while True:
            try:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break

        t_done = time.time()

        header_end = response.find(b"\r\n\r\n")
        if header_end == -1:
            print("[HTTP] Invalid response")
            return None

        headers_raw = response[:header_end].decode(errors="replace")
        body = response[header_end + 4:]
        status_line = headers_raw.split("\r\n")[0]
        
# Auto buka browser jika response adalah HTML
        if body and b"<html" in body.lower():
            import webbrowser, os
            
            # Tentukan nama file dan simpan di direktori kerja saat ini
            filename = "response_result.html"
            with open(filename, "wb") as f:
                f.write(body)
            
            # Dapatkan lokasi absolut file tersebut agar browser bisa membukanya
            abs_path = os.path.abspath(filename)
            webbrowser.open(f"file://{abs_path}")
            print(f"[HTTP] Opened in browser: {abs_path}")

        total_time = (t_done - t_start) * 1000
        connect_time = (t_connect - t_start) * 1000
        transfer_time = (t_done - t_sent) * 1000
        total_bytes = len(response)
        body_bytes = len(body)
        throughput_bps = (total_bytes * 8) / (t_done - t_start) if (t_done - t_start) > 0 else 0

        print(f"\n{'='*60}")
        print(f"[HTTP RESULT] {status_line}")
        print(f"  Path           : {path}")
        print(f"  Total bytes    : {total_bytes}")
        print(f"  Body bytes     : {body_bytes}")
        print(f"  Connect time   : {connect_time:.2f} ms")
        print(f"  Total RTT      : {total_time:.2f} ms")
        print(f"  Transfer time  : {transfer_time:.2f} ms")
        print(f"  Throughput     : {throughput_bps:.2f} bps ({throughput_bps/1000:.2f} kbps)")

        for line in headers_raw.split("\r\n")[1:]:
            if line.lower().startswith("x-proxy") or line.lower().startswith("x-server"):
                print(f"  {line}")

        print(f"{'='*60}")

        return {
            "status": status_line,
            "total_time_ms": total_time,
            "throughput_bps": throughput_bps,
            "body_size": body_bytes,
            "body": body,
        }
    except Exception as e:
        print(f"[HTTP] Error: {e}")
        return None
    finally:
        sock.close()


def udp_ping():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(PING_TIMEOUT)

    sent = 0
    received = 0
    rtts = []

    print(f"\n{'='*60}")
    print(f"[UDP PING] Target: {WEBSERVER_HOST}:{UDP_PORT}")
    print(f"[UDP PING] Sending {NUM_PINGS} packets...\n")

    for seq in range(1, NUM_PINGS + 1):
        payload = struct.pack("!Id", seq, time.time())
        try:
            send_time = time.time()
            sock.sendto(payload, (WEBSERVER_HOST, UDP_PORT))
            sent += 1

            data, addr = sock.recvfrom(1024)
            recv_time = time.time()
            received += 1

            rtt = (recv_time - send_time) * 1000
            rtts.append(rtt)

            if seq <= 5 or seq % 10 == 0 or seq == NUM_PINGS:
                print(f"  seq={seq:3d}  rtt={rtt:.3f} ms")
        except socket.timeout:
            print(f"  seq={seq:3d}  TIMEOUT")
        except Exception as e:
            print(f"  seq={seq:3d}  ERROR: {e}")

        time.sleep(0.05)

    sock.close()

    lost = sent - received
    loss_pct = (lost / sent * 100) if sent > 0 else 100

    avg_rtt = sum(rtts) / len(rtts) if rtts else 0
    min_rtt = min(rtts) if rtts else 0
    max_rtt = max(rtts) if rtts else 0

    jitter = 0
    if len(rtts) > 1:
        diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
        jitter = sum(diffs) / len(diffs)

    print(f"\n--- UDP Ping Statistics ---")
    print(f"  Sent       : {sent}")
    print(f"  Received   : {received}")
    print(f"  Lost       : {lost} ({loss_pct:.1f}%)")
    print(f"  Min RTT    : {min_rtt:.3f} ms")
    print(f"  Avg RTT    : {avg_rtt:.3f} ms")
    print(f"  Max RTT    : {max_rtt:.3f} ms")
    print(f"  Jitter     : {jitter:.3f} ms")
    print(f"{'='*60}")

    return {
        "sent": sent,
        "received": received,
        "loss_pct": loss_pct,
        "min_rtt": min_rtt,
        "avg_rtt": avg_rtt,
        "max_rtt": max_rtt,
        "jitter": jitter,
        "rtts": rtts,
    }


def run_qos_test():
    print("\n" + "#" * 60)
    print("#        QoS MEASUREMENT - NETWORK ANALYSIS")
    print("#" * 60)

    print("\n[PHASE 1] HTTP via Proxy (TCP)")
    print("-" * 40)
    http1 = http_get("/")
    time.sleep(1)

    print("\n[PHASE 2] HTTP via Proxy - QoS data endpoint")
    print("-" * 40)
    http2 = http_get("/qos-data")
    time.sleep(1)

    print("\n[PHASE 3] HTTP via Proxy - Cache test (repeat request)")
    print("-" * 40)
    http3 = http_get("/qos-data")
    time.sleep(1)

    print("\n[PHASE 4] UDP Ping (Direct to Web Server)")
    print("-" * 40)
    udp_result = udp_ping()

    print("\n" + "#" * 60)
    print("#              QoS SUMMARY REPORT")
    print("#" * 60)

    if http2:
        print(f"\n  HTTP Throughput     : {http2['throughput_bps']:.2f} bps")
        print(f"  HTTP Latency (RTT)  : {http2['total_time_ms']:.2f} ms")
    if http3:
        print(f"  HTTP Cached RTT     : {http3['total_time_ms']:.2f} ms")

    print(f"\n  UDP Packet Loss     : {udp_result['loss_pct']:.1f}%")
    print(f"  UDP Avg Latency     : {udp_result['avg_rtt']:.3f} ms")
    print(f"  UDP Jitter          : {udp_result['jitter']:.3f} ms")
    print(f"  UDP Min/Max RTT     : {udp_result['min_rtt']:.3f} / {udp_result['max_rtt']:.3f} ms")
    print("#" * 60 + "\n")


if __name__ == "__main__":
    # --- BAGIAN YANG DIUBAH MENGGUNAKAN ARGPARSE ---
    parser = argparse.ArgumentParser(description="Tubes JarKom Client Script")
    parser.add_argument('--mode', type=str, choices=['tcp', 'udp', 'qos'], help='Pilih mode protokol: tcp (HTTP), udp (Ping), atau qos')
    parser.add_argument('--path', type=str, default='/', help='Path file yang ingin diakses (cth: testing/HTML.index.html)')
    parser.add_argument('--server-host', type=str, help='IP Server/Proxy tujuan')

    # Jika script dijalankan tanpa argumen sama sekali, kita jalankan mode QoS sebagai default
    if len(sys.argv) == 1:
        run_qos_test()
        sys.exit(0)

    args = parser.parse_args()

    # Timpa global variable host jika user memasukkan --server-host
    if args.server_host:
        PROXY_HOST = args.server_host
        WEBSERVER_HOST = args.server_host

    # Jalankan fungsi sesuai mode yang dipilih
    if args.mode == 'tcp':
        http_get(args.path)
    elif args.mode == 'udp':
        udp_ping()
    elif args.mode == 'qos':
        run_qos_test()