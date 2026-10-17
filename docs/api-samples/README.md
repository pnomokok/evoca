# API samples

Example JSON responses for the REST endpoints in `docs/PROJECT.md` ("REST uçları").
The web client can be built against these files before the backend exists.
They are a **draft contract**: when the real API differs, update the sample and the doc in the same pull request.

## Conventions

- Field names and enum values are exactly those in the "Veri modeli" section (snake_case).
- IDs are opaque strings. The samples use readable IDs (`person_elif`); the real API returns UUIDs. Never parse them.
- Times are UTC ISO 8601 strings. Audio positions are integer milliseconds.
- Audio is never embedded. Play it from `/api/audio/{session_id}?start=<ms>&end=<ms>`.
- The panel fetches audio with the `X-Person-Id` header and plays it as a blob (a plain `<audio src>` cannot send the header).
  Photos work the same way: fetch `photo_url` with the header and show it as a blob URL (a plain `<img src>` cannot send it).
- The backend runs on port 8080 (`uvicorn server.app:app --port 8080`); the MCP server on port 8000 is not called by the web client.
- In `GET /api/feed`, an answer card's `answer.audio` is the answer as a list of pieces, like `audio` on the story page:
  the answer story's own pieces, with the agent's turns and private parts cut out. Play the pieces in
  order; `duration_ms` is their total. `audio_url` is the first piece only, kept for older clients.
  `audio` is `[]` and `audio_url` is `null` when the answer's session has no audio file (for example a text-only test
  session). Show the answer without a play button.
- Errors always look like `ERROR_example.json` (`{"detail": "..."}`, FastAPI's shape), with a matching HTTP status (400, 403, 404).
- Every response is already filtered by `can_see()`. The client never hides things itself; if a story is missing, the viewer may not see it.

## Who is viewing?

All panel samples are from **Elif's** point of view (granddaughter, `member`).
For the hackathon the panel opens with a password-less person picker (`GET /api/people`), and every request
carries the chosen person in an `X-Person-Id` header (PROJECT.md, decision log 17 October).

Because Elif is a plain member, these samples also show what access control hides:

- "Hatice Goes to Germany" is `private`, so it is missing from her lifeline, and `linked_stories` on the mulberry story is empty.
- "Father's Workshop" is `pending` for 24 hours, so it is missing too.
- The playlist leaves the linked private story out without a trace (no `skipped_count`: even a count would tell Elif a hidden story exists).

## Files

| File | Endpoint | Used by |
|---|---|---|
| `GET_people.json` | `GET /api/people` (**demo only**, no header) | Password-less person picker |
| `GET_circle.json` | `GET /api/circle` (new, see below) | Panel header, member list, names |
| `GET_device_invitation.json` | `GET /api/device/invitation` | Device screen: light on or off |
| `POST_device_turn.json` | `POST /api/device/turn` | Device screen: one spoken turn |
| `POST_device_turn_playlist.json` | `POST /api/device/turn` | Device screen: the elder asked to hear a story |
| `POST_device_session_end.json` | `POST /api/device/session/end` | Device screen |
| `POST_questions_accepted.json` | `POST /api/questions` | Panel question form, success |
| `POST_questions_filtered.json` | `POST /api/questions` | Panel question form, blocked by a sensitive topic |
| `GET_feed.json` | `GET /api/feed` | Panel home: answers and new stories |
| `GET_lifeline_person_fatma.json` | `GET /api/lifeline/{person_id}` | Lifeline view |
| `GET_story_mulberry.json` | `GET /api/stories/{id}` | Story page |
| `GET_story_mulberry_playlist.json` | `GET /api/stories/{id}/playlist` | "Listen from the start" |
| `POST_story_reactions.json` | `POST /api/stories/{id}/reactions` | Emoji buttons |
| `POST_story_photo.json` | `POST /api/stories/{id}/photo` | Story page: add or replace the photo |
| `POST_recordings.json` | `POST /api/recordings` | Panel: record your own memory |
| `GET_admin_sensitive_topics.json` | `GET /api/admin/sensitive-topics` (admin, Ayşe's view) | Admin: sensitive topic list |
| `POST_admin_sensitive_topics.json` | `POST /api/admin/sensitive-topics` (admin) | Admin: add a topic |
| `DELETE_admin_sensitive_topic.json` | `DELETE /api/admin/sensitive-topics/{id}` (admin) | Admin: remove a topic |
| `PATCH_admin_circle.json` | `PATCH /api/admin/circle` (admin) | Admin: chat time and timezone |
| `ERROR_example.json` | any | Error shape |

## Requests

- `GET /api/device/invitation`: `now` is the server's current time (UTC ISO 8601). It follows the demo clock
  (`DEMO_NOW`), so show the device clock from it, in the circle's timezone, not from the browser's clock.
- `POST /api/device/turn`: `multipart/form-data` with `audio` (the recorded clip) and `session_id`, the one returned by
  `POST /api/device/session/start` (call that first; it also runs the opening turn).
  `heard_text` in the response is what speech-to-text understood, for showing on screen.
  When the elder asks to hear stories ("Play me what I told about the village house"), the response has a
  `playlist` card (`POST_device_turn_playlist.json`). Play `reply_audio_url` first, then each item's `url` in order,
  with the `X-Person-Id` header like any other audio. The items are already filtered and cut around private parts;
  one story can have several items (its audio continues across them). The card appears only in the turn where the
  agent picked the stories.
- `POST /api/questions`: JSON `{"target_person_id": "...", "text": "...", "period": null}`.
  Sending the same question again (case, punctuation and a leading "Grandma,"/"Grandpa," aside) while it is unanswered returns the first question (same `id`), not a new one.
  A blocked question returns HTTP 200 with `status: "filtered"`; the message never reveals the sensitive topic itself.
  A question blocked only by a topic the center refused herself returns the normal accepted response (`status: "waiting"`); it is never asked, like an unanswered question.
- `POST /api/stories/{id}/reactions`: JSON `{"emoji": "heart", "action": "add"}` or `"remove"`. Idempotent.
  Returns which emojis are `present` on the story and which are `mine`, never counts (PROJECT.md: "Sayaç gösterilmez").
- `PATCH /api/stories/{id}/subjects/{person_id}`: JSON `{"period": "youth"}`. Anyone who can see the story.
  Returns the updated subject (`period_source: "family"`, `estimated: false`, `corrected_by`).
- `PATCH /api/stories/{id}`: JSON `{"access": "circle" | "private"}` and/or `{"hidden": true | false}`.
  Access: teller only. `hidden: true`: teller, a subject, the center or an admin. Hiding is final: `hidden: false` returns 400 for everyone.
  Returns `{id, status, access}`. Use `can_change_access` and `can_hide` from the story page to show the buttons.
- `DELETE /api/links/{id}`: marks the link `removed`; the viewer must see both stories. Returns `{id, status}`.
- `POST /api/recordings`: `multipart/form-data` with `audio`. Processing runs in the background, like a device session.
- `POST /api/stories/{id}/photo`: `multipart/form-data` with `image` (JPEG, PNG or WebP, at most 5 MB) and an optional
  `caption` (at most 120 characters). Allowed for the story's teller, any person the story is about (a subject) or an
  admin; anyone else who can see the story gets 403. One photo per story: a new upload replaces the old one.
  The server re-encodes it to a JPEG of at most 1600 px and removes all metadata (EXIF, GPS), so the client does not
  need to. Wrong type, too big or unreadable: 400. Returns `{story_id, photo_url, photo_caption}`.
- `DELETE /api/stories/{id}/photo`: the uploader, the teller or an admin. Returns the same shape with nulls.
- `GET /api/photos/{photo_id}`: the JPEG, `Cache-Control: private, no-store` (the browser keeps no copy, so a photo is gone once the story turns private or hidden). A story the viewer cannot see, or a hidden story,
  gives the same 404 as a missing photo.
- `/api/admin/*`: only the circle's `admin`; everyone else (center included) gets the same 403. Show the admin screens only when `me.role` in `GET /api/circle` is `admin`.
- `GET /api/admin/sensitive-topics` lists only topics the family added. Topics the center refused herself are never listed, and their ids get the same 404 as a missing id.
- `POST /api/admin/sensitive-topics`: JSON `{"text": "Selim's debt"}`. Empty text, or text with no word of 4+ letters the filter can match (for example "the war"), returns 400. The same text again (any case) returns the existing topic.
- `DELETE /api/admin/sensitive-topics/{id}`: questions the topic already filtered stay filtered.
- `PATCH /api/admin/circle`: JSON `{"chat_time": "09:30"}` and/or `{"timezone": "Europe/Istanbul"}` (24-hour `HH:MM`, IANA name; otherwise 400). The light follows the new time from the next scheduler pass; a day that already has its invitation is not changed.

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

- Periods carry `estimated: true` when they are an AI guess (`period_source: "ai"`); show the "estimated" label for them.
- `photo_url` and `photo_caption` are on the story page, on feed story and answer cards and on lifeline story items;
  both are `null` when the story has no photo (or is hidden). Show a placeholder then.
- Each lifeline period has `years: {from, to}`, computed from the person's `birth_year` with fixed ages: childhood 0-12,
  youth 13-22, marriage_early_years 23-30, raising_children 31-45, midlife 46-60, retirement 61+. `to` is `null` for
  retirement and when it lies after the current year; `years` is `null` when the birth year is unknown.
- `has_private_part` on the story page is `true` only for the teller, when a part they kept private overlaps this story's own audio sources. It is always `false` for everyone else.
- A story the viewer cannot see returns the same 404 as a missing one.
- `GET /api/circle` is not yet in the doc's REST table. The panel needs it for names, roles and `relation_to_center`.
- The feed's `question_answered` item uses a story that is not in the seed yet ("Walking to School in the Snow"). It shows the shape of the answer card.
- `gaps` in the lifeline is computed from the stories the **viewer** can see, so it never hints that a hidden story exists.
- Period labels for the UI (for example `marriage_early_years` → "Early marriage") are the web client's job.
