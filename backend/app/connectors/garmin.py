from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class GarminConnectorStatus:
    official_api_available: bool
    manual_import_available: bool
    non_official_enabled: bool
    message: str


def garmin_status() -> GarminConnectorStatus:
    settings = get_settings()
    return GarminConnectorStatus(
        official_api_available=False,
        manual_import_available=True,
        non_official_enabled=settings.garmin_non_official_enabled,
        message=(
            "Official Garmin Health/Activity/Training API support is adapter-ready but requires "
            "approved Garmin Connect Developer Program credentials. Manual metrics and file imports "
            "are available now."
        ),
    )
