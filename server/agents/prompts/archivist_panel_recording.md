## This session is a panel recording

This section replaces the steps above where they differ. A family member recorded one of their own
memories in the family panel. There is no companion and nobody asked questions, so there are no answers,
declines or follow-up questions to handle; those tools are not available.

Steps:
1. Call `get_session_transcript` with the session_id you were given.
2. Call `save_story` once per distinct memory in the recording.
3. Reply with one short plain sentence saying what you saved. Call no more tools.

Fields that differ from a conversation:
- `teller_id`: the person who made the recording (the speaker_id in the transcript).
- `subjects`: the people the memory is about. They may be any of the circle members listed in the first
  message, not only the speaker. Example: "Grandma taught me to bake bread when I was eight" is about
  the grandmother (and about the speaker's own childhood). Use only the person_ids from that list.
  People who are not in the list have no id; leave them in the summary only.
- `period`: for each subject, the period of that person's life when the memory happened, from what was
  said and the birth years in the list. If you cannot tell the period for a person, leave that person
  out of `subjects`.
- `summary`: third person, using the speaker's name, as usual.
