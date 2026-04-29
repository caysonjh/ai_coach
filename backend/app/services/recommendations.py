from app.models.entities import GearItem, GearType, Sport, SportVariant, TrainingLocation, WorkoutLocationFeedback


def rank_locations(
    locations: list[TrainingLocation],
    feedback: list[WorkoutLocationFeedback],
    sport: Sport,
    sport_variant: SportVariant,
    intensity: str,
    limit: int = 5,
) -> list[dict]:
    feedback_by_location: dict[int, list[WorkoutLocationFeedback]] = {}
    for item in feedback:
        feedback_by_location.setdefault(item.location_id, []).append(item)

    scored: list[tuple[float, TrainingLocation, list[WorkoutLocationFeedback]]] = []
    for location in locations:
        if not location.active or location.sport != sport:
            continue
        score = 1.0
        if location.sport_variant == sport_variant:
            score += 1.5
        elif location.sport_variant == SportVariant.other:
            score += 0.25
        if intensity.lower() in location.tags.lower() or intensity.lower() in location.location_notes.lower():
            score += 0.5
        local_feedback = feedback_by_location.get(location.id or -1, [])
        if local_feedback:
            score += sum(item.rating for item in local_feedback) / len(local_feedback)
            score -= sum(1 for item in local_feedback if not item.use_again) * 0.75
        scored.append((score, location, local_feedback))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "name": location.name,
            "score": round(score, 2),
            "sport": location.sport.value,
            "sport_variant": location.sport_variant.value,
            "surface": location.surface,
            "notes": location.location_notes,
            "recent_feedback": [
                {"rating": item.rating, "stimulus": item.intended_stimulus, "notes": item.notes}
                for item in local_feedback[-3:]
            ],
        }
        for score, location, local_feedback in scored[:limit]
    ]


def recommend_gear(gear: list[GearItem], sport: Sport, sport_variant: SportVariant, surface: str | None) -> dict | None:
    desired_type = GearType.shoes if sport == Sport.run else GearType.bike if sport == Sport.bike else None
    if desired_type is None:
        return None

    candidates = [item for item in gear if item.active and item.gear_type == desired_type]
    if not candidates:
        return None

    def score(item: GearItem) -> float:
        value = 0.0
        if sport_variant.value in item.preferred_sport_variants:
            value += 2.0
        if surface and surface.lower() in item.preferred_surfaces.lower():
            value += 1.0
        if item.retire_distance_meters:
            remaining_ratio = max(0, item.retire_distance_meters - item.distance_meters) / item.retire_distance_meters
            value += remaining_ratio
        value -= item.distance_meters / 1_000_000
        return value

    selected = max(candidates, key=score)
    return {
        "name": selected.name,
        "gear_type": selected.gear_type.value,
        "distance_miles": round(selected.distance_meters / 1609.344, 1),
        "rationale": (
            f"Best local match for {sport_variant.value}; current mileage is "
            f"{round(selected.distance_meters / 1609.344, 1)} mi."
        ),
    }
