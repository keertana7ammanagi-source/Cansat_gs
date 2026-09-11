"""
TELEMETRY SIMULATOR — for testing without hardware.
"""
import time
import random
import sys

TEAM_ID = "2026-INSPACe-CAN-7USAT-036"

def build_fake_packet(pkt_num, elapsed_seconds, state=5):
    alt = 700.0 + random.uniform(-5, 5)
    press = 940.0 + random.uniform(-2, 2)
    temp = 24.0 + random.uniform(-1, 1)
    volt = 7.6 + random.uniform(-0.05, 0.05)
    hum = 45.0 + random.uniform(-5, 5)
    uv = 3.0 + random.uniform(-1, 1)
    light = 200.0 + random.uniform(-50, 50)
    rotor = 2150.0 + random.uniform(-100, 100)
    ax, ay, az = 0.12, 0.08, 9.81
    gr, gp, gy = 12.4, 8.7, 3.2
    mag_r, mag_p, mag_y = 0.18, 0.05, 0.41
    lat = 28.6129 + random.uniform(-0.0005, 0.0005)
    lon = 77.2295 + random.uniform(-0.0005, 0.0005)
    gps_alt = alt
    sats = 9
    cmd_echo = "OK"

    h = elapsed_seconds // 3600
    m = (elapsed_seconds % 3600) // 60
    s = elapsed_seconds % 60
    t_str = f"{h:02d}:{m:02d}:{s:02d}"

    fields = [
        TEAM_ID, t_str, str(pkt_num),
        f"{alt:.1f}", f"{press:.1f}", f"{temp:.1f}", f"{volt:.2f}",
        t_str, f"{lat:.4f}", f"{lon:.4f}", f"{gps_alt:.1f}", str(sats),
        f"{ax:.2f}", f"{ay:.2f}", f"{az:.2f}",
        f"{gr:.2f}", f"{gp:.2f}", f"{gy:.2f}",
        str(state),
        f"{hum:.1f}", f"{uv:.1f}", f"{light:.1f}", f"{rotor:.0f}",
        f"{mag_r:.2f}", f"{mag_p:.2f}", f"{mag_y:.2f}",
        "1", cmd_echo
    ]
    return ",".join(fields)

def run_with_virtual_serial(port_name):
    import serial
    ser = serial.Serial(port_name, 115200, timeout=1)
    print(f"Simulator writing to {port_name}. Connect GUI to the paired port.")
    pkt = 0
    start = time.time()
    try:
        while True:
            pkt += 1
            elapsed = int(time.time() - start)
            line = build_fake_packet(pkt, elapsed)
            ser.write((line + "\n").encode())
            print("SENT:", line)
            time.sleep(1)
    except KeyboardInterrupt:
        ser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python telemetry_simulator.py COMx")
        sys.exit(1)
    run_with_virtual_serial(sys.argv[1])