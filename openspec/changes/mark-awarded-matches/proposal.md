# Proposal

## Why

Fourteen matches in our sources were decided off the pitch, by a forfeit or a disciplinary decision, and openfootball tags them `[awarded]`. The tag is dropped after parsing, so the API shows them as ordinary results. Thirteen carry the awarded score (for example `0-2 [awarded]`). SC Bastia v Olympique Lyonnais (Ligue 1 2016-17) carries only the 0–0 at abandonment. That matches the LFP's record: the official table credits Lyon with the win but no goals. Against Wikipedia's conventional 3–0, though, it is a permanent `MISMATCH` that no source will ever resolve.

## What Changes

- **`awarded` on matches.** `true` when the source tags the result `[awarded]` (text) or `"status": "awarded"` (JSON mirror), otherwise `false`. It's stored and returned in match responses. Scores stay exactly as the source records them.
- **Verification of awarded matches.**
  - An awarded match whose stored score is level gets no verification status. The source names no winner, so there is nothing to compare with a reference that records the awarded result. Bastia v Lyon leaves `MISMATCH`.
  - Awarded matches with a decisive score are compared as before. All of them verify today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `matches`: Match record gains `awarded`.
- `match-verification`: Verification status per match. Awarded matches with a level score are not compared.

## Impact

- **Database:** an Alembic migration adds `match.awarded` (boolean, default `false`).
- **Code:** the text parser and JSON reader keep the tag, the sync stores it, the verifier skips level awarded matches, and the API schema exposes it.
- **API:** additive (`awarded` on match objects).
- **Data:** the next sync sets `awarded` on the 14 tagged matches, and the next verified run removes Bastia v Lyon's `MISMATCH`.
