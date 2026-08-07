"""Phase controller used by market and task policy."""

def phase(day):
    if day <= 4:
        return "bootstrap"
    if day <= 15:
        return "compound"
    if day <= 25:
        return "mature"
    return "liquidation"

def order_budget(day, money, animals, hands):
    p = phase(day)
    future_hands = {"bootstrap": 5, "compound": 12, "mature": 12, "liquidation": 4}[p]
    worker_buffer = max(0, future_hands - hands) * 8
    feed_buffer = animals * max(2, 30 - day)
    emergency = 400 if p != "liquidation" else 0
    return max(0, money - worker_buffer - feed_buffer - emergency)

def production_targets(day):
    p = phase(day)
    if p == "bootstrap":
        return {"hands": min(4, 2 + day), "cows": min(3, 1 + day), "sheep": 0, "straw": 0}
    if p == "compound":
        return {"hands": 12, "cows": min(10, 3 + day // 2), "sheep": max(0, day - 10), "straw": min(6, max(0, day - 8))}
    if p == "mature":
        return {"hands": 12, "cows": 10, "sheep": 8, "straw": 6}
    return {"hands": 4, "cows": 10, "sheep": 8, "straw": 6}
