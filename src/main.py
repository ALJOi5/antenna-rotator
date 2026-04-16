import serial
import math
import tkinter as tk
from tkintermapview import TkinterMapView
import requests
import threading
import time

from sats import HamSatTracker

rotator = serial.Serial("COM8", 115200)

target_lat = None
target_lon = None
base_alt = 0
marker = None
iss_marker = None
RADIJ_ZEMLE = 6371000
ready = threading.Event()
ready.set()

iss_lat = None
iss_lon = None

def wrt(ld, gd):
    rotator.write(f"{ld:.2f} {gd:.2f}\n".encode())

def bearing_3d(c1, c2):
    lat1, lon1, h1 = c1
    lat2, lon2, h2 = c2
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    lon1 = math.radians(lon1)
    lon2 = math.radians(lon2)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = (math.cos(lat1)*math.sin(lat2) -
         math.sin(lat1)*math.cos(lat2)*math.cos(dlon))
    bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
    a = (math.sin((lat2-lat1)/2)**2 +
         math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2)
    tla_dist = 2 * RADIJ_ZEMLE * math.atan2(math.sqrt(a), math.sqrt(1-a))
    dh = h2 - h1
    visina = math.degrees(math.atan2(dh, tla_dist))
    return bearing, visina

def map_clicked(coords):
    global target_lat, target_lon, marker
    target_lat, target_lon = coords
    print("Target:", target_lat, target_lon)
    if marker is not None:
        marker.delete()
    marker = map_widget.set_marker(target_lat, target_lon)

def update_iss_marker():
    global iss_marker
    if iss_lat is None:
        return
    if iss_marker is None:
        iss_marker = map_widget.set_marker(iss_lat, iss_lon, text="ISS")
    else:
        iss_marker.set_position(iss_lat, iss_lon)

def fetch_and_point():
    global base_alt, iss_lat, iss_lon
    if target_lat is None:
        return
    try:
        current_alt = float(alt_entry.get() or 0)
        tracker = HamSatTracker(lat=target_lat, lon=target_lon, alt_m=current_alt)
        closest = tracker.satellites[0]
        lat = closest.lat
        lon = closest.lon
        alt = closest.alt_km * 1000
        print(f"{closest.name}:", lat, lon, alt)
        iss_lat = lat
        iss_lon = lon
        root.after(0, update_iss_marker)
        if ready.is_set():
            base_alt = current_alt
            bearing, elevation = bearing_3d(
                (target_lat, target_lon, base_alt),
                (lat, lon, alt)
            )
            print("Send:", bearing, elevation)
            ready.clear()
            wrt(bearing, elevation)
    except Exception as e:
        print("Error:", e)

def wait_for_ack():
    while True:
        try:
            line = rotator.readline().decode().strip()
            if line == "OK":
                print("Rotator ready")
                ready.set()
        except:
            pass

def read_radio():
    t = threading.Thread(target=fetch_and_point, daemon=True)
    t.start()
    root.after(5000, read_radio) 

root = tk.Tk()
root.geometry("900x650")
map_widget = TkinterMapView(root, width=900, height=550)
map_widget.pack()
map_widget.set_position(46.0569, 14.5058)
map_widget.set_zoom(1)
map_widget.add_left_click_map_command(map_clicked)
frame = tk.Frame(root)
frame.pack(pady=5)
tk.Label(frame, text="Base altitude (m):").pack(side=tk.LEFT)
alt_entry = tk.Entry(frame)
alt_entry.insert(0, "0")
alt_entry.pack(side=tk.LEFT)
threading.Thread(target=wait_for_ack, daemon=True).start()
root.after(1000, read_radio)
root.mainloop()