"""DWD AICON (AI model) adapter: official DWD open data is published, point ingestion is not enabled.

Investigation (2026-10-01): AICON runs are published on DWD open data at
  https://opendata.dwd.de/weather/nwp/v1/m/aicon/p/<PARAM>/r/<run>/s/PT<lead>H00M.grib2
with T_2M, U_10M, V_10M, TOT_PREC, RELHUM_2M (and more), 4 runs/day, 3-hourly steps to 180 h.
The GRIB2 files use the native ICON icosahedral grid (grid definition template 101, grid 26,
~2.95 M cells) with CCSDS packing (template 42). Extracting a point value needs an ecCodes/libaec
decoder plus DWD's separate grid-coordinate file, and ~3 MB per variable per lead time. That is a
new GRIB toolchain this project does not have, so AICON values are not ingested.

`probe()` reads the official run listing on every refresh so the UI shows the latest real run
that DWD has published, without producing any forecast values.
"""

import re
from urllib.parse import unquote

import httpx

from app.config import DWD_AICON_RUNS_URL
from app.schemas.weather import ModelDescriptor, Provenance, ProviderForecast
from app.services.weather.forecast_provider import ForecastProvider, ProviderUnavailableError

REASON = (
    "Official DWD AICON GRIB2 is on the native ICON icosahedral grid (CCSDS-compressed); "
    "point extraction needs a GRIB decoder and grid file that are not currently enabled in TrustCast."
)


def parse_run_listing(html: str) -> list[str]:
    """Run directories (e.g. 2026-10-01T12:00) from a DWD open-data directory listing."""
    runs = {unquote(m) for m in re.findall(r'href="([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}(?:%3A|:)[0-9]{2})/"', html)}
    return sorted(runs)


class AICONProvider(ForecastProvider):
    descriptor = ModelDescriptor(
        name="DWD AICON",
        model_type="AI weather model",
        provider="DWD",
        status="unavailable",
        source="DWD open data (opendata.dwd.de, AICON GRIB2)",
        source_url="https://opendata.dwd.de/weather/nwp/v1/m/aicon/",
        source_type="official_catalogue",
        variables=["temperature", "precipitation", "wind_speed", "humidity"],
        note="Official run published; point extraction from the native icosahedral GRIB2 is not currently enabled in TrustCast.",
    )

    async def get_forecast(self, latitude: float, longitude: float, forecast_days: int) -> ProviderForecast:
        raise ProviderUnavailableError(self.descriptor.note or REASON)

    async def probe(self) -> Provenance:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(DWD_AICON_RUNS_URL)
            response.raise_for_status()
            runs = parse_run_listing(response.text)
            steps = None
            if runs:
                step_listing = await client.get(f"{DWD_AICON_RUNS_URL}{runs[-1].replace(':', '%3A')}/s/")
                if step_listing.status_code == 200:
                    steps = len(re.findall(r'href="PT[0-9]+H[0-9]+M\.grib2"', step_listing.text))
        return {
            "official_source": DWD_AICON_RUNS_URL,
            "latest_run_published": runs[-1] if runs else None,
            "runs_listed": len(runs),
            "lead_time_files_in_latest_run": steps,
            "format": "GRIB2 · ICON icosahedral grid 26 · CCSDS packing",
            "reason": REASON,
        }
