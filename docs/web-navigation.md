# Web navigation

How a person reaches every function of the web client, before and after the navigation rework
(branch `zeynep/navigation`). Two layers:

- **Product layer**: what a real family sees. The same in demo mode and when signed in.
- **Demo layer**: one thin "Demo" strip above the product (never when signed in, never on the landing page).
  It is the only place that switches person, opens the stage, moves the demo clock or exits the demo.

## Pages and URLs

| Path | Page | Who |
| --- | --- | --- |
| `/` | Landing | Everyone. Signed in: "Open your family" instead of the demo buttons. |
| `/demo/loop` | Stage ("Watch the loop") | Demo only (signed in: goes to `/archive/journal`). |
| `/archive/journal` | Family journal | Everyone with a family. Demo: the center person goes to `/device`. |
| `/archive/chapters` | Life chapters | As the journal. |
| `/archive/questions` | My questions | Not the center person. |
| `/archive/story/:id` | Story (a sub-page, not a tab) | Anyone who can see the story; otherwise the existing "Not available" page. |
| `/archive/settings` | Family settings | Admin only (anyone else goes to `/archive/journal`). |
| `/device` | Living room device, full screen | Demo: the center person. Signed in: only the center; anyone else goes to `/archive/journal`. |
| `/join/:token` | Join page | Unchanged; ends on `/archive/journal` (or `/device` for the center). |
| anything else | | `/`, or `/archive/journal` when signed in. |

The router lives in the app context (`web/src/context/AppContext.jsx`, paths in `web/src/utils/routes.js`).
Navigation pushes history; Back and Forward restore the page, the story's back target and (demo only) the person
viewing, which is kept in the history entry's state, never in the URL. Stage panes (`?embed=...`) never touch history.

## Inventory

"Before" is every way to reach a function on `main` (`bf27308`). "After" is its one place now.
✓ = checked in the browser after the change (Edge via Playwright, 1366 and 390 px, demo and signed in).

### Entry, identity and demo

| Function | Before (button text · component · file) | After | ✓ |
| --- | --- | --- | --- |
| Open the demo | "Try the Demo" (landing nav), "Watch & Try Demo" (hero), "Experience the Loop" (how it works), "Explore Privacy Controls in Panel" (privacy), "Open Family Archive" (closing CTA), "Try the Demo" (footer) · `LandingPage.jsx`; each opened `DemoEntryModal` | "Try the demo" in the landing header, the hero and the closing CTA; each opens the demo modal. The section and footer buttons are removed. | ✓ |
| Open the device directly from the landing | "Living Room Device" (landing nav, hero), "Living Room Device Screen" (closing CTA) · `LandingPage.jsx` | **Removed.** The device opens from the person picker (choose the storyteller). | ✓ |
| Demo modal: watch the loop | "Watch the loop" · `DemoEntryModal.jsx` | Same, recommended; goes to `/demo/loop`. | ✓ |
| Demo modal: pick a role | "Pick a role" · `DemoEntryModal.jsx` (opened the panel) | "Explore as a family member": opens the person picker. | ✓ |
| Switch person (demo) | `<select>` "Viewing as" · `DemoHeader.jsx`; click a person in the family tree · `FamilyTreeCard.jsx`; "Pick a role" on the stage bar · `StageView.jsx` | Only "Viewing as <first name>" in the demo strip, which opens the person picker. Choosing the storyteller opens `/device`, anyone else `/archive/journal`. | ✓ |
| Archive as seen by the center (demo) | Pick Fatma in the select; note "talks to Evoca on the Living Room Device" · `FamilyPanel.jsx` | **Removed** in demo: picking her opens the device. Signed-in center: unchanged (the note stays, it is her own device). | ✓ |
| Create your family | "Ready to keep your own family's stories?" band · `App.jsx`; "Create your family" · `DemoHeader.jsx` | "Create your family" (secondary) in the landing header and the closing CTA. The band and the archive header button are removed. | ✓ |
| Join link | `/join/:token` · `JoinPage.jsx` | Unchanged; "Join" ends on `/archive/journal` (or `/device` for the center), "Go to Evoca" on `/`. | ✓ |
| Leave (signed in) | "Leave" · `DemoHeader.jsx` | "Leave" next to the person's name in the archive header; on mobile in the header menu. Ends on `/`. | ✓ |
| Open your family (signed in, from the landing) | Brand / "Family Archive" nav · `DemoHeader.jsx` | "Open your family" in the landing header, hero and closing CTA. | ✓ |
| Overview / landing | "Overview" nav and the brand · `DemoHeader.jsx`; brand on the stage bar · `StageView.jsx` | The archive brand: `/archive/journal` when signed in, `/` in the demo. "Exit demo" in the demo strip. | ✓ |
| Demo clock (+1 hour, next morning, +1 day) | Clock chip menu · `DemoControls.jsx` in `DemoHeader.jsx`; inline buttons on the stage bar | Demo strip: the clock chip menu (inline buttons on the stage). Mobile: inside the "Demo" button. | ✓ |
| Reset demo | "Reset demo" in the clock menu / "Reset" on the stage bar · `DemoControls.jsx` | Same, in the demo strip. Stays on the page (a story goes back to the journal; on the device the storyteller stays selected). | ✓ |
| Watch the loop | Stage via the demo modal; "Pick a role" leaves it | `/demo/loop`: demo modal, and "Watch the loop" in the demo strip. Panes unchanged. | ✓ |
| Living room device | "Living Room Device" top nav · `DemoHeader.jsx`; "Open the Living Room Device" · `FamilyPanel.jsx` | `/device`, full screen. Demo: via the person picker. Signed-in center: her home after joining, and her note in the archive. | ✓ |
| Exit demo | (none; "Overview") | "Exit demo" in the demo strip → `/`. | ✓ |

### Family archive

| Function | Before (button text · component · file) | After | ✓ |
| --- | --- | --- | --- |
| Journal | "Family Journal" pill · `FamilyPanel.jsx`; "Journal" mobile tab | Header tab "Journal"; mobile bottom bar "Journal". `/archive/journal`. | ✓ |
| Life chapters | "Life Chapters" pill; "Chapters" mobile tab; "See Fatma's life chapters →" and "View the life chapters" · `FamilyTreeModal.jsx` | Header tab "Life chapters"; mobile "Chapters"; "View the life chapters" in the full family tree (the duplicate link in the same dialog is removed). `/archive/chapters`. | ✓ |
| My questions | "My questions" pill; "Questions" mobile tab | Header tab "My questions"; mobile "Questions". `/archive/questions`. | ✓ |
| Family settings (admin): sensitive topics, chat time, members, invite links | "Family settings" pill (desktop only) · `FamilyPanel.jsx` → `FamilySettings.jsx`, `MembersSection.jsx` | Header tab "Family settings" (admin only); mobile header menu. `/archive/settings`. | ✓ |
| Story detail | "Story Detail" pill and "Story" mobile tab · `FamilyPanel.jsx` | **Tab removed.** The story is a sub-page `/archive/story/:id`, opened from a story. | ✓ |
| Ask a question | "Ask a Question" · `FamilyPanel.jsx`; "Ask Fatma a question" (journal hero) and "Ask a question" (journal footer) · `FamilyDashboard.jsx`; "Ask Fatma a question" · `MyQuestions.jsx`; "Ask" mobile tab | Header "Ask a question" (primary); mobile bottom bar "Ask". The duplicates in the journal and My questions are removed. | ✓ |
| Ask about a chapter (with period and prompt) | Chapter cards "+ Ask this question" · `FamilyDashboard.jsx`; "Ask about this chapter" · `LifelineView.jsx` | Unchanged (contextual). | ✓ |
| Record memory | "Record Memory" · `FamilyPanel.jsx`; "Record your own memory" (journal footer), "Record the first one today →" and "+" · `FamilyTreeCard.jsx` | Header "Record memory"; mobile header menu. The journal footer, the tree link and the tree "+" are removed. | ✓ |
| Family tree, full view | "Full view" · `FamilyTreeCard.jsx` → `FamilyTreeModal.jsx` | Unchanged; the tree is informative only (no person switching). | ✓ |
| Open a story | Journal: featured "Listen to the story", "Read the full story", card title, "Listen", "Read the story →", activity "Listen to the recording" · `FamilyDashboard.jsx`; Life chapters: title, "Listen and read" · `LifelineView.jsx`; linked stories, retellings · `StoryView.jsx` | Same links; each opens `/archive/story/:id` and remembers where it came from. | ✓ |
| Back from a story | "Back to the journal" (always) · `StoryView.jsx` | "← Back to the journal" / "← Back to life chapters" / "← Back to my questions", matching the page it was opened from; browser Back does the same. | ✓ |
| Listen, listen from the start, speed, restart, transcript seek | `StoryView.jsx` | Unchanged on the story page. | ✓ |
| React to a story | Reaction buttons · `StoryView.jsx`, `AnswerCard.jsx` | Unchanged. | ✓ |
| Add a photo | "Add a photo" · `StoryView.jsx` → `AddPhotoModal.jsx` | Unchanged. | ✓ |
| Hide a story | "Hide" · `StoryView.jsx` | Unchanged; afterwards the journal (replacing the story in history). | ✓ |
| Period correction | Chapter pill → "Change the chapter" · `StoryView.jsx`; "Which chapter does this story belong to?" · `LifelineView.jsx` | Unchanged. | ✓ |
| Who can see a story | "Who can see it" select · `StoryView.jsx` | Unchanged. | ✓ |
| Remove a wrong link | "Not related" · `StoryView.jsx` | Unchanged. | ✓ |
| Lifeline filters | All / Stories / Gaps · `LifelineView.jsx` | Unchanged. | ✓ |
| Open an answer from My questions | Answer card, "Open the story that answers it →" · `MyQuestions.jsx` | Same; the story's back button says "Back to my questions". | ✓ |
| Answer cards (play, react) | `AnswerCard.jsx` in the journal and My questions | Unchanged. | ✓ |

### Device

| Function | Before | After | ✓ |
| --- | --- | --- | --- |
| Talk, hold to speak, stop, hear again, goodbye, invitation, privacy moment, trace | `DeviceScreen.jsx` under the product header | Same, full screen at `/device` without a product header. Demo: the demo strip above it. | ✓ (screen checked; talking needs AWS and was not run; the component is unchanged) |
