import requests
from config import OPENCELLID_API_KEY

BASE_URL = "https://opencellid.org/cell/get"

class CellLookupError(Exception):
    """Raised when OpenCellID lookup fails."""

def lookup_cell(mcc: str, mnc: str, lac: str, cell_id: str) -> dict:
    """
    Query OpenCellID untuk posisi BTS.

    Args:
        mcc: Mobile Country Code (3 digit)
        mnc: Mobile Network Code (2-3 digit)
        lac: Location Area Code
        cell_id: Cell ID

    Returns:
        dict dengan keys: lat, lon, range, mcc, mnc, lac, cellid

    Raises:
        CellLookupError: kalau BTS nggak ketemu atau API error.
    """
    params = {
        "key": OPENCELLID_API_KEY,
        "mcc": mcc,
        "mnc": mnc,
        "lac": lac,
        "cellid": cell_id,
        "format": "json",
    }

    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise CellLookupError(f"Request gagal: {e}") from e

    data = resp.json()

    if "lat" not in data or "lon" not in data:
        raise CellLookupError(
            f"BTS tidak ditemukan di database. Response: {data}"
        )

    return {
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
        "range": int(data.get("range", 0)),
        "mcc": data.get("mcc", mcc),
        "mnc": data.get("mnc", mnc),
        "lac": data.get("lac", lac),
        "cellid": data.get("cellid", cell_id),
    }
