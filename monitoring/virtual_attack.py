import random
import socket
import threading
import time
from contextlib import closing
from typing import Iterable, Optional

# Loopback-only demo addresses.
# These stay on the local machine and are safe for IDS demo traffic.
ATTACKER_IP = "127.0.0.2"
TARGET_IP = "127.0.0.1"

# Use ports that make sense for your demo.
# 8000 is useful if your API is running there; the others are there for scan noise.
SCAN_PORTS = list(range(20, 200))
BURST_PORTS = [8000, 8080, 9000, 9999]


def _make_tcp_socket(source_ip: str, timeout: float = 0.2) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.bind((source_ip, 0))
    return s


def _make_udp_socket(source_ip: str) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((source_ip, 0))
    return s


def _try_tcp_connect(target_ip: str, target_port: int, source_ip: str, timeout: float = 0.2) -> None:
    s = _make_tcp_socket(source_ip, timeout=timeout)
    try:
        s.connect((target_ip, target_port))
    finally:
        s.close()


def tcp_port_scan(
    target_ip: str = TARGET_IP,
    source_ip: str = ATTACKER_IP,
    ports: Iterable[int] = SCAN_PORTS,
    delay_s: float = 0.002,
) -> None:
    print(f"Simulating TCP port scan from {source_ip} -> {target_ip}")
    for port in ports:
        try:
            _try_tcp_connect(target_ip, port, source_ip, timeout=0.05)
        except OSError:
            pass
        time.sleep(delay_s)


def tcp_connect_burst(
    target_ip: str = TARGET_IP,
    source_ip: str = ATTACKER_IP,
    target_ports: Iterable[int] = BURST_PORTS,
    duration_s: float = 5.0,
    delay_s: float = 0.001,
) -> None:
    print(f"Simulating TCP connection burst from {source_ip} -> {target_ip}")
    end_time = time.time() + duration_s
    ports = list(target_ports) or [8000]

    while time.time() < end_time:
        port = random.choice(ports)
        try:
            _try_tcp_connect(target_ip, port, source_ip, timeout=0.02)
        except OSError:
            pass
        time.sleep(delay_s)


def udp_flood(
    target_ip: str = TARGET_IP,
    source_ip: str = ATTACKER_IP,
    target_port: int = 9999,
    duration_s: float = 5.0,
    payload_size: int = 512,
    delay_s: float = 0.0005,
) -> None:
    print(f"Simulating UDP flood from {source_ip} -> {target_ip}:{target_port}")
    end_time = time.time() + duration_s
    payload = b"A" * payload_size

    with closing(_make_udp_socket(source_ip)) as sock:
        while time.time() < end_time:
            try:
                sock.sendto(payload, (target_ip, target_port))
            except OSError:
                pass
            time.sleep(delay_s)


def http_flood(
    target_ip: str = TARGET_IP,
    source_ip: str = ATTACKER_IP,
    target_port: int = 8000,
    duration_s: float = 5.0,
    delay_s: float = 0.001,
) -> None:
    print(f"Simulating HTTP flood from {source_ip} -> {target_ip}:{target_port}")
    end_time = time.time() + duration_s
    request = (
        b"GET / HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"User-Agent: IDS-Demo\r\n"
        b"Connection: close\r\n\r\n"
    )

    while time.time() < end_time:
        try:
            s = _make_tcp_socket(source_ip, timeout=0.2)
            try:
                s.connect((target_ip, target_port))
                s.sendall(request)
            finally:
                s.close()
        except OSError:
            pass
        time.sleep(delay_s)


def bandwidth_spike(
    target_ip: str = TARGET_IP,
    source_ip: str = ATTACKER_IP,
    target_port: int = 8000,
    duration_s: float = 6.0,
    chunk_size: int = 4096,
) -> None:
    print(f"Simulating bandwidth spike from {source_ip} -> {target_ip}:{target_port}")
    payload = b"A" * chunk_size
    end_time = time.time() + duration_s

    try:
        s = _make_tcp_socket(source_ip, timeout=0.2)
        s.connect((target_ip, target_port))
    except OSError:
        print(f"Could not connect to {target_ip}:{target_port}. Start your local server first.")
        return

    try:
        while time.time() < end_time:
            try:
                s.sendall(payload)
            except OSError:
                break
    finally:
        s.close()


def simulate_attack(attack_type: str = "syn") -> None:
    attack_type = String = str(attack_type).strip().lower()

    if attack_type == "scan":
        tcp_port_scan()
    elif attack_type == "syn":
        tcp_connect_burst()
    elif attack_type == "udp":
        udp_flood()
    elif attack_type == "http":
        http_flood()
    elif attack_type == "bandwidth":
        bandwidth_spike()
    else:
        print(f"Unknown attack type: {attack_type}")


def auto_attack_loop(stop_event: threading.Event, pause_s: float = 8.0) -> None:
    attacks = ["scan", "syn", "udp", "http", "bandwidth"]

    while not stop_event.is_set():
        simulate_attack(random.choice(attacks))
        stop_event.wait(pause_s)


def main() -> None:
    print("Starting virtual attacker...")
    stop_event = threading.Event()

    thread = threading.Thread(
        target=auto_attack_loop,
        args=(stop_event,),
        daemon=True,
    )
    thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        thread.join(timeout=2)
        print("Virtual attacker stopped.")


if __name__ == "__main__":
    main()