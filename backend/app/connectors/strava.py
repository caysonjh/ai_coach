from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlmodel import Session

from app.core.config import get_settings
from app.models.entities import Activity, GearItem, GearType, OAuthAccount, Source, Sport, SportVariant


SPORT_MAP = {
    "Run": Sport.run,
    "TrailRun": Sport.run,
    "Ride": Sport.bike,
    "VirtualRide": Sport.bike,
    "GravelRide": Sport.bike,
    "Swim": Sport.swim,
    "WeightTraining": Sport.strength,
    "RockClimbing": Sport.climb,
}

VARIANT_MAP = {
    "Run": SportVariant.road_run,
    "TrailRun": SportVariant.trail_run,
    "Ride": SportVariant.road_ride,
    "VirtualRide": SportVariant.tt_ride,
    "GravelRide": SportVariant.gravel_ride,
    "MountainBikeRide": SportVariant.mtb_ride,
    "Swim": SportVariant.pool_swim,
}


class StravaConnector:
    def __init__(self) -> None:
        self.settings = get_settings()

    def authorization_url(self) -> str:
        params = {
            "client_id": self.settings.strava_client_id,
            "redirect_uri": self.settings.strava_redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": "activity:read_all,profile:read_all",
        }
        return f"https://www.strava.com/oauth/authorize?{urlencode(params)}"

    async def exchange_code(self, session: Session, code: str) -> OAuthAccount:
        payload = {
            "client_id": self.settings.strava_client_id,
            "client_secret": self.settings.strava_client_secret,
            "code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://www.strava.com/oauth/token", data=payload)
            response.raise_for_status()
            data = response.json()

        account = OAuthAccount(
            provider="strava",
            athlete_id=str(data.get("athlete", {}).get("id", "")),
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=datetime.utcfromtimestamp(data["expires_at"]),
            scopes="activity:read_all,profile:read_all",
            raw_payload=data,
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        return account

    async def sync_recent_activities(self, session: Session, account: OAuthAccount, days: int = 90) -> int:
        token = await self._valid_access_token(session, account)
        after = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        imported = 0
        page = 1
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                response = await client.get(
                    "https://www.strava.com/api/v3/athlete/activities",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"after": after, "page": page, "per_page": 100},
                )
                response.raise_for_status()
                batch = response.json()
                if not batch:
                    break
                for item in batch:
                    session.add(self._activity_from_strava(item))
                    imported += 1
                page += 1
        session.commit()
        return imported

    async def sync_gear(self, session: Session, account: OAuthAccount) -> int:
        token = await self._valid_access_token(session, account)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://www.strava.com/api/v3/athlete",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            athlete = response.json()

        count = 0
        for item in athlete.get("shoes", []):
            self._upsert_gear(session, item, GearType.shoes)
            count += 1
        for item in athlete.get("bikes", []):
            self._upsert_gear(session, item, GearType.bike)
            count += 1
        session.commit()
        return count

    async def _valid_access_token(self, session: Session, account: OAuthAccount) -> str:
        if account.expires_at and account.expires_at > datetime.utcnow() + timedelta(minutes=2):
            return account.access_token
        payload = {
            "client_id": self.settings.strava_client_id,
            "client_secret": self.settings.strava_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": account.refresh_token,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://www.strava.com/oauth/token", data=payload)
            response.raise_for_status()
            data = response.json()
        account.access_token = data["access_token"]
        account.refresh_token = data["refresh_token"]
        account.expires_at = datetime.utcfromtimestamp(data["expires_at"])
        account.updated_at = datetime.utcnow()
        session.add(account)
        session.commit()
        return account.access_token

    def _activity_from_strava(self, item: dict) -> Activity:
        strava_sport = item.get("sport_type") or item.get("type")
        sport = SPORT_MAP.get(strava_sport, Sport.other)
        return Activity(
            source=Source.strava,
            source_id=str(item.get("id")),
            sport=sport,
            sport_variant=VARIANT_MAP.get(strava_sport, SportVariant.other),
            gear_id=item.get("gear_id"),
            name=item.get("name") or "Strava Activity",
            start_time=datetime.fromisoformat(item["start_date"].replace("Z", "+00:00")),
            duration_seconds=item.get("moving_time") or item.get("elapsed_time") or 0,
            distance_meters=item.get("distance"),
            elevation_meters=item.get("total_elevation_gain"),
            avg_hr=item.get("average_heartrate"),
            max_hr=item.get("max_heartrate"),
            avg_power=item.get("average_watts"),
            max_power=item.get("max_watts"),
            calories=item.get("calories"),
            raw_payload=item,
        )

    def _upsert_gear(self, session: Session, item: dict, gear_type: GearType) -> None:
        from sqlmodel import select

        strava_id = item.get("id")
        existing = session.exec(
            select(GearItem).where(GearItem.strava_gear_id == strava_id)
        ).first()
        gear = existing or GearItem(
            strava_gear_id=strava_id,
            name=item.get("name") or item.get("nickname") or "Strava Gear",
            gear_type=gear_type,
            source=Source.strava,
        )
        gear.name = item.get("name") or item.get("nickname") or gear.name
        gear.distance_meters = item.get("distance") or gear.distance_meters or 0
        gear.active = not bool(item.get("retired"))
        gear.raw_payload = item
        if not gear.retire_distance_meters and gear_type == GearType.shoes:
            gear.retire_distance_meters = 500 * 1609.344
        session.add(gear)
