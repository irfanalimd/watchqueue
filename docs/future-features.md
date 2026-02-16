# Future Features Roadmap

This roadmap focuses on high-impact additions after the current core is in place (rooms, queue, voting, wheel selection, reactions, history, realtime).

## 1. Streaming Availability + "Play Now" Links
Problem: Winning an item that nobody can actually watch reduces trust quickly.

Plan:
- Enrich queue items with region-specific provider availability (Netflix, Prime Video, etc.) and deep links.
- Show an "Available to X/Y members" indicator.
- Allow filtering queue by provider and "available now".

Backend:
- Extend TMDB enrichment flow to include watch provider data by region.
- Store provider metadata on queue items.
- Add filtering support in queue endpoints.

Frontend:
- Add provider badges/chips on each queue card.
- Show "Play Now" CTA on the selected winner card.
- Add a quick "only show available" toggle.

Expected impact:
- Fewer dead-end selections.
- Faster time-to-watch.

## 2. Guided Voting Rounds (Lock, Countdown, Auto-Pick)
Problem: Sessions stall when voting has no clear start/end structure.

Plan:
- Introduce explicit round states: `idle`, `voting`, `selection_pending`, `selected`.
- Lock queue mutations while voting is active.
- Display countdown and auto-trigger selection when timer ends.

Backend:
- Persist round state and timer metadata.
- Reuse existing selection endpoint when round expires.

Frontend:
- Top voting banner with live countdown.
- Disable add/remove actions during locked phase.
- Smooth transition into wheel spin on timeout.

Expected impact:
- Faster decisions.
- Lower coordination overhead.

## 3. Host Controls + Safety Rails
Problem: Open rooms become noisy (spam queue adds, accidental removals, bad actor behavior).

Plan:
- Add lightweight roles (`host`, `member`) and room-level permissions.
- Typical controls: who can remove others' items, who can start rounds, per-user queue limits.

Backend:
- Add role/permission checks to queue/voting/selection operations.
- Keep defaults permissive for simple use, configurable for larger groups.

Frontend:
- Host badge and host-only controls.
- Clear permission denied toasts/messages.

Expected impact:
- Better quality in active group sessions.
- Fewer social conflicts in-room.

## 4. Group Taste Engine (Smart Suggestions)
Problem: Users still manually search each round and repeat discovery effort.

Plan:
- Build suggestions based on watch history, ratings, reactions, and vote patterns.
- Add explainability tags (e.g., "Because your group liked Interstellar").

Backend:
- Recommendation service combining metadata similarity + collaborative group signals.
- New endpoint for room-specific suggestions.

Frontend:
- "Suggested for your group" section with one-click add to queue.
- Optional feedback controls (more like this / less like this).

Expected impact:
- Less decision friction.
- Better picks over time.

## 5. Session Summary + Decision Analytics
Problem: Groups cannot easily learn from previous sessions.

Plan:
- Generate per-session summary (top candidates, winner, participation, satisfaction signals).
- Add room-level trends (genre hit rate, pick fairness, engagement over time).

Backend:
- Persist round/session events and aggregate analytics views.
- Expose summary/trend endpoints.

Frontend:
- Session recap view after watch.
- Insights tab in history sidebar.

Expected impact:
- Better long-term retention.
- Clear evidence that the app improves with usage.

## Suggested Implementation Order
1. Streaming Availability + "Play Now" Links
2. Guided Voting Rounds
3. Host Controls + Safety Rails
4. Group Taste Engine
5. Session Summary + Decision Analytics

