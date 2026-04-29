from datetime import date

from app.models.entities import (
    GearItem,
    GearType,
    Source,
    Sport,
    SportVariant,
    TrainingLocation,
    WorkoutLocationFeedback,
)
from app.services.recommendations import rank_locations, recommend_gear


def test_rank_locations_prefers_matching_variant_and_feedback() -> None:
    location = TrainingLocation(
        id=1,
        name="Back Bay",
        sport=Sport.run,
        sport_variant=SportVariant.trail_run,
        surface="trail",
        tags="easy aerobic",
    )
    feedback = WorkoutLocationFeedback(
        location_id=1,
        feedback_date=date(2026, 4, 29),
        intended_stimulus="easy aerobic",
        rating=5,
    )
    ranked = rank_locations([location], [feedback], Sport.run, SportVariant.trail_run, "easy")
    assert ranked[0]["name"] == "Back Bay"
    assert ranked[0]["score"] > 5


def test_recommend_gear_prefers_matching_surface_and_variant() -> None:
    shoe = GearItem(
        name="Trail Shoe",
        gear_type=GearType.shoes,
        distance_meters=100 * 1609.344,
        retire_distance_meters=500 * 1609.344,
        preferred_sport_variants="trail_run",
        preferred_surfaces="trail",
        source=Source.manual,
    )
    rec = recommend_gear([shoe], Sport.run, SportVariant.trail_run, "trail")
    assert rec
    assert rec["name"] == "Trail Shoe"
