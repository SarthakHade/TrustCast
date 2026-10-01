"""NCMRWF NCUM-G provider adapter: real official source checked, no machine-readable point values.

Investigation (2026-09-30 / 2026-10-01):
  * SWFDP page https://nwp.ncmrwf.gov.in/HomePage/NEPS-prod-1.php POSTs to `get_tabimages.php`
    and loads rendered PNG charts from `Data/mihir/<date>/<cycle>/<variable>/` (image/png).
  * The NCMRWF web app uses the JSON API https://nwp.ncmrwf.gov.in/apis/api/v1:
      GET forecast/all-models                -> model_id 1 = "ncum-g" (global, 10 days)
      GET forecast/forecast-products?model_id=1 -> Wind-Forecast, Rain-Forecast, Meteogram, ...
      GET forecast-products/getForecastHours?model_id=1&forecast_product_id=<id> -> lead hours
    These describe chart products (the app names them *_MODEL_CHARTS); the Meteogram product
    lists no forecast hours, and no endpoint returns numeric point values (GRIB/NetCDF/JSON).
  * rds.ncmrwf.gov.in is the IMDAA reanalysis portal (registration-based), not NCUM forecasts.

So NCUM-G stays "unavailable": no values are generated, scored, weighted or blended. `probe()`
queries the official API on every refresh so the UI shows what NCMRWF currently publishes, and
the adapter can be switched to real ingestion as soon as a machine-readable feed is available.
"""

import httpx

from app.config import NCMRWF_API_URL
from app.schemas.weather import ModelDescriptor, Provenance, ProviderForecast
from app.services.weather.forecast_provider import ForecastProvider, ProviderUnavailableError

OFFICIAL_PRODUCT_URL = "https://nwp.ncmrwf.gov.in/HomePage/NEPS-prod-1.php"
REASON = "Official NCMRWF API publishes NCUM-G chart products only; no machine-readable point-forecast feed is available."

# TrustCast field -> official SWFDP product (VariableID on the NCMRWF page) for future ingestion.
# Precipitation is published as 6-h accumulations, so an hourly series would need explicit
# disaggregation, which is deliberately NOT done here.
OFFICIAL_PRODUCTS = {
    "temperature": (2, "Temperature at 2m"),
    "wind_speed": (1, "Winds at 10m"),
    "humidity": (5, "RH at 2m"),
    "precipitation": (7, "6-hrs Accumulated Precipitation"),
}


def summarize_catalogue(models: dict, products: dict, hours: dict[str, list[int]]) -> Provenance:
    """Turn official NCMRWF API responses into provenance (no forecast values involved)."""
    ncum = next((m for m in models.get("models", []) if m.get("model_abbreviation") == "ncum-g"), None)
    names = [p.get("product_name") for p in products.get("products", []) if p.get("active")]
    summary: Provenance = {
        "official_api": NCMRWF_API_URL,
        "model_listed": f"{ncum['model_abbreviation']} · {ncum['model_name']} · {ncum['duration']}" if ncum else None,
        "products": ", ".join(n for n in names if n) or None,
        "machine_readable_point_data": False,
        "reason": REASON,
    }
    for product, values in hours.items():
        summary[f"{product}_hours"] = f"{min(values)}–{max(values)} h ({len(values)} steps)" if values else "none listed"
    return summary


class NCUMProvider(ForecastProvider):
    descriptor = ModelDescriptor(
        name="NCUM-G",
        model_type="Physics NWP",
        provider="NCMRWF / MoES",
        status="unavailable",
        source="NCMRWF official forecast API (chart products)",
        source_url=OFFICIAL_PRODUCT_URL,
        source_type="official_catalogue",
        variables=["temperature", "precipitation", "wind_speed", "humidity"],
        note="Official NCMRWF source checked: no machine-readable NCUM-G point-forecast feed is published, so no values are used.",
    )

    async def get_forecast(self, latitude: float, longitude: float, forecast_days: int) -> ProviderForecast:
        raise ProviderUnavailableError(self.descriptor.note or REASON)

    async def probe(self) -> Provenance:
        async with httpx.AsyncClient(timeout=20.0, headers={"Accept": "application/json"}) as client:
            models = (await client.get(f"{NCMRWF_API_URL}/forecast/all-models")).json()
            ncum = next((m for m in models.get("models", []) if m.get("model_abbreviation") == "ncum-g"), None)
            model_id = ncum["model_id"] if ncum else 1
            products = (await client.get(f"{NCMRWF_API_URL}/forecast/forecast-products", params={"model_id": model_id})).json()
            hours: dict[str, list[int]] = {}
            for product in products.get("products", []):
                if product.get("product_name") in ("Rain-Forecast", "Wind-Forecast", "Meteogram"):
                    reply = await client.get(
                        f"{NCMRWF_API_URL}/forecast-products/getForecastHours",
                        params={"model_id": model_id, "forecast_product_id": product["id"]},
                    )
                    hours[product["product_name"]] = reply.json().get("forecastHours", []) if reply.status_code == 200 else []
        return summarize_catalogue(models, products, hours)
