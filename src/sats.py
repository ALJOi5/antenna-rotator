import requests
import math
from dataclasses import dataclass


N2YO_API_KEY = "FYBCDW-Q3G3B5-JXBJ2R-5P18"
N2YO_BASE = "https://api.n2yo.com/rest/v1/satellite"

HAM_SATS = [
    (61781, "TEST",   "UPL", "DWNL", "FM"),

]


@dataclass
class Satellite:
    norad: int
    name: str
    uplink: str
    downlink: str
    mode: str
    lat: float = 0.0
    lon: float = 0.0
    alt_km: float = 0.0
    azimuth: float = 0.0
    elevation: float = 0.0
    range_km: float = float("inf")


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


class HamSatTracker:
    def __init__(self, lat: float, lon: float, alt_m: float = 0):
        self.lat = lat
        self.lon = lon
        self.alt_m = alt_m
        self.satellites: list[Satellite] = []
        self._fetch_all()

    def _get(self, endpoint: str) -> dict:
        url = f"{N2YO_BASE}{endpoint}&apiKey={N2YO_API_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _fetch_position(self, norad: int) -> dict | None:
        try:
            data = self._get(f"/positions/{norad}/{self.lat}/{self.lon}/{int(self.alt_m)}/1")
            positions = data.get("positions")
            return positions[0] if positions else None
        except Exception:
            return None

    def _fetch_all(self):
        for norad, name, uplink, downlink, mode in HAM_SATS:
            sat = Satellite(norad=norad, name=name, uplink=uplink, downlink=downlink, mode=mode)
            pos = self._fetch_position(norad)
            if pos:
                sat.lat = pos.get("satlatitude", 0.0)
                sat.lon = pos.get("satlongitude", 0.0)
                sat.alt_km = pos.get("sataltitude", 0.0)
                sat.azimuth = pos.get("azimuth", 0.0)
                sat.elevation = pos.get("elevation", 0.0)
                surface = _haversine_km(self.lat, self.lon, sat.lat, sat.lon)
                sat.range_km = math.sqrt(surface ** 2 + sat.alt_km ** 2)
            self.satellites.append(sat)
        self.satellites.sort(key=lambda s: s.range_km)

    def _compass(self, deg: float) -> str:
        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
        return dirs[round(deg / 22.5) % 16]

    def print(self):
        W = [26, 12, 13, 7, 9, 10, 9, 13, 8, 12]
        headers = ["Name", "Uplink MHz", "Downlink MHz", "Mode", "Lat", "Lon", "Alt km", "Azimuth", "El°", "Range km"]
        total = sum(W) + len(W) * 3 + 1
        sep = "─" * total

        def row(*vals):
            r = "│"
            for v, w in zip(vals, W):
                r += f" {str(v):<{w}} │"
            return r

        print(f"\n  🛰  Ham Satellites — sorted by slant range from {self.lat}°N {self.lon}°E\n")
        print(sep)
        print(row(*headers))
        print(sep)

        for sat in self.satellites:
            rng = f"{sat.range_km:.0f}" if sat.range_km != float("inf") else "N/A"
            az = f"{sat.azimuth:.0f}° {self._compass(sat.azimuth)}"
            print(row(
                sat.name,
                sat.uplink,
                sat.downlink,
                sat.mode,
                f"{sat.lat:.2f}°",
                f"{sat.lon:.2f}°",
                f"{sat.alt_km:.0f}",
                az,
                f"{sat.elevation:.1f}°",
                rng,
            ))

        print(sep)
        print()


if __name__ == "__main__":
    tracker = HamSatTracker(lat=46.0511, lon=14.5051, alt_m=295)
    tracker.print()