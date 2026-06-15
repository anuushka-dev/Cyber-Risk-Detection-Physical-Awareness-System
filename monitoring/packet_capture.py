# monitoring/packet_capture.py
import logging
from typing import Callable, Optional

logger = logging.getLogger("monitor.packet_capture")

def start_packet_capture(callback: Callable[..., None], interface: Optional[str] = None, promisc: bool = True):
    try:
        # import local to allow import even if scapy not installed
        from scapy.all import sniff
        from scapy.layers.inet import IP, TCP, UDP
    except Exception as e:
        logger.exception("Scapy not available or failed import")
        raise

    def process_packet(pkt):
        try:
            if IP not in pkt:
                return
            ip = pkt[IP]
            ts = float(getattr(pkt, "time", 0.0))
            proto = None
            sport = None
            dport = None
            flags = None
            tcp_window = 0
            payload_len = 0
            if TCP in pkt:
                t = pkt[TCP]
                proto = "TCP"
                sport = int(t.sport)
                dport = int(t.dport)
                # flags as string like 'S', 'SA', etc.
                flags = str(t.flags)
                tcp_window = int(getattr(t, "window", 0))
                # payload length: TCP payload bytes (if any)
                payload_len = len(bytes(t.payload)) if t.payload is not None else 0
            elif UDP in pkt:
                u = pkt[UDP]
                proto = "UDP"
                sport = int(u.sport)
                dport = int(u.dport)
                flags = ""
                payload_len = len(bytes(u.payload)) if u.payload is not None else 0
            else:
                # ignore non-TCP/UDP IP packets for this IDS
                return

            callback(
                src_ip=str(ip.src),
                dst_ip=str(ip.dst),
                src_port=sport,
                dst_port=dport,
                protocol=proto,
                length=len(pkt),
                flags=flags,
                timestamp=ts,
                tcp_window=tcp_window,
                payload_len=payload_len
            )
        except Exception:
            logger.exception("Error processing packet")

    sniff_kwargs = dict(prn=process_packet, store=False)
    if interface:
        sniff_kwargs["iface"] = interface
    # promisc flag mapping depends; scapy may use it via sniff param if underlying lib supports it
    # start capture (this will block the calling thread)
    logger.info("Starting packet capture on iface=%s promisc=%s", interface, promisc)
    sniff(**sniff_kwargs)
    # Backwards compatibility: some code may import PacketCapture
    PacketCapture = start_packet_capture