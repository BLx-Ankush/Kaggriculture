# v22 route research oracle

The attached notebook contains a verified 18,609-byte `main.py` artifact with SHA-256:
`62fb5a5f66f0011092a2b51e3192879ba583d5d815d761f176091c615657147a`.
It reports a live-engine score of about 2904 and explicitly says its headline 44/46 metric
is frozen counterfactual replay, not an official leaderboard score.

## Recovered route footprint

- day 0: five hires, two cows, two sheep, 12 melon seeds, seven wheat seeds
- day 3: 12 melon, 7 wheat, 2 pens, 2 cows, 2 sheep
- day 9: 12 melon, 7 wheat, 12 strawberry, 6 cows, 4 sheep
- day 12: 12 melon, 7 wheat, 39 strawberry, 8 cows, 6 sheep
- day 15 to 21: 42 strawberry, 8 cows, 6 sheep, third quadrant
- final week: convert strawberry tiles into wheat
- hands: 1 day 5, 8 day 10, 13 day 15, 14 days 20 to 25

## Important mechanism

Strawberry has the strongest shop demand: 24 units/day once all shops unlock. Wheat is the
cash valve and remains near twice its base price late because five shops demand it. Melon has
no shop demand, so it is an opening cash crop, not the mature-farm product.

## Changes in this branch

`kagg_core.py`, `kagg_plan.py`, and `kagg_market.py` now use this route as a closed-loop research
oracle rather than copying the notebook's fixed 719-step tape. The agent still needs a local
official-engine benchmark before promotion. Do not treat the notebook's 44/46 number as LB
performance, and do not submit the fixed tape blindly: its own mirror test ties and its edge
will decay as more teams fork it.
