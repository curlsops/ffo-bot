import random


def select_weighted_winners(entries: list, count: int) -> list:
    if not entries or count < 1:
        return []

    weighted = []
    for entry in entries:
        weighted.extend([entry["user_id"]] * entry["entries"])

    random.shuffle(weighted)
    winners = []
    seen = set()
    for user_id in weighted:
        if user_id not in seen:
            winners.append(user_id)
            seen.add(user_id)
        if len(winners) >= count:
            break

    return winners
