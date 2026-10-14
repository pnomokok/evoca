// Evoca Mock API Data Store
// Aligned exactly with docs/*.json and docs/README.md

export const initialCircle = {
  circle: {
    id: "circle_yilmaz",
    name: "The Yilmaz Family",
    center_person_id: "person_fatma",
    status: "active",
    chat_time: "10:00",
    timezone: "Europe/Istanbul"
  },
  me: {
    id: "person_elif",
    name: "Elif Yilmaz",
    role: "member",
    relation_to_center: "granddaughter"
  },
  members: [
    { id: "person_fatma", name: "Fatma Yilmaz", birth_year: 1948, role: "center", relation_to_center: null, avatar: "👵" },
    { id: "person_ayse",  name: "Ayşe Yilmaz",  birth_year: 1975, role: "admin",  relation_to_center: "daughter", avatar: "👩" },
    { id: "person_elif",  name: "Elif Yilmaz",  birth_year: 2003, role: "member", relation_to_center: "granddaughter", avatar: "👧" },
    { id: "person_can",   name: "Can Yilmaz",   birth_year: 2006, role: "member", relation_to_center: "grandson", avatar: "👦" }
  ]
};

export const initialDeviceInvitation = {
  active: true,
  invitation: {
    id: "invitation_today",
    person_id: "person_fatma",
    date: "2026-10-14",
    reason: "Elif has a question for you.",
    status: "sent"
  }
};

export const initialDeviceTurn = {
  session_id: "session_demo1",
  session_open: true,
  heard_text: "Alexa, what's new?",
  reply_text: "Good morning, Fatma! Elif laughed a lot at your mulberry tree story. And your granddaughter Elif would love to know: what was school like when you were young?",
  reply_audio_url: null, // synthesized on the fly via browser SpeechSynthesis / AudioContext
  cards: [
    {
      type: "reaction",
      story_id: "story_mulberry",
      story_title: "The Mulberry Tree",
      from: { id: "person_elif", name: "Elif Yilmaz", relation_to_center: "granddaughter" },
      emoji: "laugh"
    },
    {
      type: "question",
      question_id: "question_school",
      text: "Grandma, what was school like when you were young?",
      asker: { id: "person_elif", name: "Elif Yilmaz", relation_to_center: "granddaughter" }
    }
  ]
};

export const initialFeed = {
  items: [
    {
      type: "question_answered",
      created_at: "2026-10-14T08:05:00+00:00",
      question: {
        id: "question_school",
        text: "Grandma, what was school like when you were young?",
        asker_id: "person_elif"
      },
      answer: {
        story_id: "story_school",
        story_title: "Walking to School in the Snow",
        teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
        session_id: "session_demo2",
        start_ms: 61000,
        end_ms: 118500,
        duration_ms: 57500,
        ai_summary: "Fatma describes how they used to walk 4 kilometers in deep snow to reach the village primary school, carrying hot potatoes in their pockets to keep their hands warm.",
        audio_url: "/api/audio/session_demo2?start=61000&end=118500"
      }
    },
    {
      type: "story_published",
      created_at: "2026-10-13T16:00:00+00:00",
      story: {
        id: "story_mulberry",
        title: "The Mulberry Tree",
        ai_summary: "Fatma recalls climbing the mulberry tree with her sister every summer as a child in their village garden.",
        teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
        subjects: [ { person_id: "person_fatma", period: "childhood", period_source: "ai" } ],
        duration_ms: 22000
      }
    }
  ]
};

export const initialLifeline = {
  person: { id: "person_fatma", name: "Fatma Yilmaz", birth_year: 1948, relation_to_center: null },
  periods: [
    {
      period: "childhood",
      title: "Childhood (0-12)",
      stories: [
        {
          id: "story_mulberry",
          title: "The Mulberry Tree",
          ai_summary: "Fatma recalls climbing the mulberry tree with her sister every summer as a child in their village garden.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "ai",
          status: "published",
          duration_ms: 22000
        },
        {
          id: "story_school",
          title: "Walking to School in the Snow",
          ai_summary: "Carrying hot baked potatoes in pockets during harsh winter treks to the one-room schoolhouse.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "family",
          status: "published",
          duration_ms: 57500
        }
      ]
    },
    { period: "youth", title: "Youth (13-20)", stories: [] },
    { period: "marriage_early_years", title: "Early Marriage", stories: [] },
    { period: "raising_children", title: "Raising Children", stories: [] },
    { period: "midlife", title: "Midlife", stories: [] },
    { period: "retirement", title: "Retirement", stories: [] }
  ],
  gaps: ["youth", "marriage_early_years", "raising_children", "midlife", "retirement"]
};

export const initialStoryMulberry = {
  id: "story_mulberry",
  circle_id: "circle_yilmaz",
  title: "The Mulberry Tree",
  ai_summary: "Fatma recalls climbing the mulberry tree with her sister every summer as a child in their village garden.",
  kind: "original",
  original_story_id: null,
  status: "published",
  teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
  subjects: [
    { person_id: "person_fatma", name: "Fatma Yilmaz", period: "childhood", period_source: "ai", corrected_by: null }
  ],
  place: "Village of Akçaabat, Trabzon",
  stated_year: null,
  access: { type: "circle", person_ids: [] },
  can_change_access: false,
  audio: [
    {
      session_id: "session_demo1",
      start_ms: 0,
      end_ms: 22000,
      url: "/api/audio/session_demo1?start=0&end=22000"
    }
  ],
  transcript: [
    {
      segment_id: "segment_1",
      speaker: { id: "person_fatma", name: "Fatma Yilmaz" },
      start_ms: 0,
      end_ms: 22000,
      text: "When I was a little girl in the village, we had a big mulberry tree in the garden. Every summer we would climb it and eat until our hands turned purple.",
      words: [
        { w: "When", start_ms: 0, end_ms: 450 },
        { w: "I", start_ms: 460, end_ms: 650 },
        { w: "was", start_ms: 660, end_ms: 950 },
        { w: "a", start_ms: 960, end_ms: 1100 },
        { w: "little", start_ms: 1110, end_ms: 1550 },
        { w: "girl", start_ms: 1560, end_ms: 2100 },
        { w: "in", start_ms: 2110, end_ms: 2300 },
        { w: "the", start_ms: 2310, end_ms: 2500 },
        { w: "village,", start_ms: 2510, end_ms: 3300 },
        { w: "we", start_ms: 3600, end_ms: 3850 },
        { w: "had", start_ms: 3860, end_ms: 4200 },
        { w: "a", start_ms: 4210, end_ms: 4350 },
        { w: "big", start_ms: 4360, end_ms: 4800 },
        { w: "mulberry", start_ms: 4810, end_ms: 5500 },
        { w: "tree", start_ms: 5510, end_ms: 6100 },
        { w: "in", start_ms: 6110, end_ms: 6350 },
        { w: "the", start_ms: 6360, end_ms: 6550 },
        { w: "garden.", start_ms: 6560, end_ms: 7400 },
        { w: "Every", start_ms: 7900, end_ms: 8400 },
        { w: "summer", start_ms: 8410, end_ms: 9000 },
        { w: "we", start_ms: 9010, end_ms: 9250 },
        { w: "would", start_ms: 9260, end_ms: 9600 },
        { w: "climb", start_ms: 9610, end_ms: 10200 },
        { w: "it", start_ms: 10210, end_ms: 10500 },
        { w: "and", start_ms: 10510, end_ms: 10750 },
        { w: "eat", start_ms: 10760, end_ms: 11200 },
        { w: "until", start_ms: 11210, end_ms: 11700 },
        { w: "our", start_ms: 11710, end_ms: 11950 },
        { w: "hands", start_ms: 11960, end_ms: 12600 },
        { w: "turned", start_ms: 12610, end_ms: 13200 },
        { w: "purple.", start_ms: 13210, end_ms: 14200 }
      ]
    }
  ],
  retellings: [
    {
      id: "story_ayse_mulberry",
      title: "Mom's Purple Stained Clothes",
      teller: { id: "person_ayse", name: "Ayşe Yilmaz", relation_to_center: "daughter" },
      relation_note: "Retelling with a daughter's perspective on how grandmother always complained about the laundry"
    }
  ],
  linked_stories: [
    {
      link_id: "link_village_house",
      reason: "same_place",
      source: "ai",
      status: "suggested",
      story: {
        id: "story_village_house",
        title: "Building the Stone Oven in Akçaabat",
        teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null }
      }
    }
  ],
  reactions: {
    counts: { heart: 2, laugh: 3, sad: 0, pray: 1 },
    mine: ["laugh"]
  },
  publish_at: "2026-10-13T16:00:00+00:00",
  created_at: "2026-10-13T15:05:00+00:00"
};

export const initialStoryMulberryPlaylist = {
  story_id: "story_mulberry",
  items: [
    {
      story_id: "story_mulberry",
      title: "The Mulberry Tree",
      teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
      period: "childhood",
      session_id: "session_demo1",
      start_ms: 0,
      end_ms: 22000,
      url: "/api/audio/session_demo1?start=0&end=22000"
    },
    {
      story_id: "story_village_house",
      title: "Building the Stone Oven in Akçaabat",
      teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
      period: "childhood",
      session_id: "session_demo3",
      start_ms: 0,
      end_ms: 38000,
      url: "/api/audio/session_demo3?start=0&end=38000"
    }
  ],
  skipped_count: 1 // One private story ("Hatice Goes to Germany") skipped automatically
};

export const SENSITIVE_TOPIC_KEYWORDS = [
  "1977 traffic",
  "traffic accident",
  "accident in 1977",
  "kazası",
  "trafik kazası",
  "lawsuit",
  "inheritance dispute",
  "miras"
];
