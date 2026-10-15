# API samples

Example JSON responses for the REST endpoints in `docs/PROJECT.md` ("REST uçları").
The web client can be built against these files before the backend exists.
They are a **draft contract**: when the real API differs, update the sample and the doc in the same pull request.

## Conventions

- Field names and enum values are exactly those in the "Veri modeli" section (snake_case).
- IDs are opaque strings. The samples use readable IDs (`person_elif`); the real API returns UUIDs. Never parse them.
- Times are UTC ISO 8601 strings. Audio positions are integer milliseconds.
- Audio is never embedded. Play it from `/api/audio/{session_id}?start=<ms>&end=<ms>`.
- Errors always look like `ERROR_example.json`, with a matching HTTP status (400, 403, 404).
- Every response is already filtered by `can_see()`. The client never hides things itself; if a story is missing, the viewer may not see it.

## Who is viewing?

All panel samples are from **Elif's** point of view (granddaughter, `member`).
How the panel identifies the viewer is still an open decision (see "Açık kararlar").
Until then, the backend reads the viewer from an `X-Person-Id` request header.

Because Elif is a plain member, these samples also show what access control hides:

- "Hatice Goes to Germany" is `private`, so it is missing from her lifeline, and `linked_stories` on the mulberry story is empty.
- "Father's Workshop" is `pending` for 24 hours, so it is missing too.
- The playlist reports `skipped_count: 1` for the linked private story.

## Files

| File | Endpoint | Used by |
|---|---|---|
| `GET_circle.json` | `GET /api/circle` (new, see below) | Panel header, member list, names |
| `GET_device_invitation.json` | `GET /api/device/invitation` | Device screen: light on or off |
| `POST_device_turn.json` | `POST /api/device/turn` | Device screen: one spoken turn |
| `POST_device_session_end.json` | `POST /api/device/session/end` | Device screen |
| `POST_questions_accepted.json` | `POST /api/questions` | Panel question form, success |
| `POST_questions_filtered.json` | `POST /api/questions` | Panel question form, blocked by a sensitive topic |
| `GET_feed.json` | `GET /api/feed` | Panel home: answers and new stories |
| `GET_lifeline_person_fatma.json` | `GET /api/lifeline/{person_id}` | Lifeline view |
| `GET_story_mulberry.json` | `GET /api/stories/{id}` | Story page |
| `GET_story_mulberry_playlist.json` | `GET /api/stories/{id}/playlist` | "Listen from the start" |
| `POST_story_reactions.json` | `POST /api/stories/{id}/reactions` | Emoji buttons |
| `POST_recordings.json` | `POST /api/recordings` | Panel: record your own memory |
| `ERROR_example.json` | any | Error shape |

## Requests

- `POST /api/device/turn`: `multipart/form-data` with `audio` (the recorded clip) and `session_id` (empty on the first turn).
  `heard_text` in the response is what speech-to-text understood, for showing on screen.
- `POST /api/questions`: JSON `{"target_person_id": "...", "text": "...", "period": null}`.
  A blocked question returns HTTP 200 with `status: "filtered"`; the message never reveals the sensitive topic itself.
- `POST /api/stories/{id}/reactions`: JSON `{"emoji": "heart", "action": "add"}` or `"remove"`. Returns the new counts.
- `POST /api/recordings`: `multipart/form-data` with `audio`. Processing runs in the background, like a device session.

## Shapes not shown with data

Some lists are empty for Elif. When they have items, they look like this:

```json
"linked_stories": [
  {
    "link_id": "link_1",
    "reason": "same_place",
    "source": "ai",
    "status": "suggested",
    "story": { "id": "story_x", "title": "...", "teller": { "id": "person_fatma", "name": "Fatma Yilmaz", "relation_to_center": null } }
  }
],
"retellings": [
  { "id": "story_y", "title": "...", "teller": { "id": "person_ayse", "name": "Ayşe Yilmaz", "relation_to_center": "daughter" } }
]
```

## Notes

- `GET /api/circle` is not yet in the doc's REST table. The panel needs it for names, roles and `relation_to_center`.
- The feed's `question_answered` item uses a story that is not in the seed yet ("Walking to School in the Snow"). It shows the shape of the answer card.
- `gaps` in the lifeline is computed from the stories the **viewer** can see, so it never hints that a hidden story exists.
- Period labels for the UI (for example `marriage_early_years` → "Early marriage") are the web client's job.
