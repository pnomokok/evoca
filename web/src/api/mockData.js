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
    { id: "person_ayse",  name: "Ayse Yilmaz",  birth_year: 1975, role: "admin",  relation_to_center: "daughter", avatar: "👩" },
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
  reply_audio_url: null,
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
        period: "childhood",
        period_label: "Childhood",
        photo_url: "/school_winter.jpg",
        session_id: "session_demo2",
        start_ms: 61000,
        end_ms: 118500,
        duration_ms: 57500,
        excerpt: "Four kilometers in knee-deep snow. Mother would slip two hot baked potatoes straight from the wood stove into our coat pockets so our fingers wouldn't freeze on the walk.",
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
        teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
        period: "childhood",
        period_label: "Childhood",
        photo_url: "/mulberry_memory.jpg",
        excerpt: "When I was a little girl in the village, we had a big mulberry tree in the garden. Every summer we would climb it and eat until our hands turned purple.",
        ai_summary: "Fatma recalls climbing the mulberry tree with her sister every summer as a child in their village garden.",
        subjects: [ { person_id: "person_fatma", period: "childhood", period_source: "ai" } ],
        duration_ms: 22000
      }
    }
  ]
};

export const initialLifeline = {
  person: { id: "person_fatma", name: "Fatma Yilmaz", birth_year: 1948, relation_to_center: null, avatar_url: "/grandma_fatma.jpg" },
  periods: [
    {
      period: "childhood",
      title: "Childhood (0-12)",
      era: "1948 – 1960",
      description: "Growing up in the mountain village of Akcaabat, climbing mulberry trees, and snowy school treks.",
      invitationPrompt: "What was your childhood home like during the winter months?",
      stories: [
        {
          id: "story_mulberry",
          title: "The Mulberry Tree",
          year: 1956,
          place: "Village of Akcaabat, Trabzon",
          photo_url: "/mulberry_memory.jpg",
          photo_caption: "The village garden, 1956",
          ai_summary: "Fatma recalls climbing the mulberry tree with her sister every summer as a child in their village garden.",
          excerpt: "When I was a little girl in the village, we had a big mulberry tree in the garden. Every summer we would climb it and eat until our hands turned purple.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "ai",
          status: "published",
          duration_ms: 22000
        },
        {
          id: "story_school",
          title: "Walking to School in the Snow",
          year: 1958,
          place: "Highland Trail to School",
          photo_url: "/school_winter.jpg",
          photo_caption: "Winter trail to schoolhouse, 1958",
          ai_summary: "Carrying hot baked potatoes in pockets during harsh winter treks to the one-room schoolhouse.",
          excerpt: "Four kilometers in knee-deep snow. Mother would slip two hot baked potatoes straight from the wood stove into our coat pockets so our fingers wouldn't freeze on the walk.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "family",
          status: "published",
          duration_ms: 58000
        }
      ]
    },
    {
      period: "youth",
      title: "Youth & Discovery (13-20)",
      era: "1961 – 1967",
      description: "Teenage days helping at the harbor bazaar, autumn olive harvests, and seaside songs.",
      invitationPrompt: "What music or radio programs did you and your friends love to listen to?",
      stories: [
        {
          id: "story_bazaar",
          title: "The Friday Tea Bazaar",
          year: 1963,
          place: "Akcaabat Port Market",
          photo_url: "/bazaar_memory.jpg",
          photo_caption: "Akcaabat port market, 1963",
          ai_summary: "Visiting the lively Friday harbor market with her father to trade handpicked tea sacks and roasted hazelnuts.",
          excerpt: "Every Friday morning before sunrise, the harbor smelled of roasted hazelnuts and fresh black tea leaves brought down from the mountain terraces.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "family",
          status: "published",
          duration_ms: 48000
        },
        {
          id: "story_olive",
          title: "Autumn Olive Harvest",
          year: 1965,
          place: "Hillside Olive Orchard",
          photo_url: "/olive_memory.jpg",
          photo_caption: "Hillside olive orchard, 1965",
          ai_summary: "Community traditions and folk songs during the late October olive harvest on the hills overlooking the sea.",
          excerpt: "The entire village gathered when the first autumn rains touched the branches. We sang folk melodies while spreading burlap sheets under ancient trees.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "ai",
          status: "published",
          duration_ms: 52000
        }
      ]
    },
    {
      period: "marriage_early_years",
      title: "Early Adulthood & Marriage",
      era: "1968 – 1972",
      description: "Leaving the inland village to build a seaside home and start a life with Grandfather Hasan.",
      invitationPrompt: "How did you and Grandpa first meet, and who made the first move?",
      stories: [
        {
          id: "story_coast",
          title: "The Summer We Moved to the Coast",
          year: 1968,
          place: "Akcaabat Coastal Cottage",
          photo_url: "/coast_memory.jpg",
          photo_caption: "Akcaabat coastal cottage, 1968",
          ai_summary: "Fatma recounts moving to the Black Sea coast after marriage, settling into their stone cottage by the shore.",
          excerpt: "We packed two wooden trunks with olive oil tins, dried figs, and my mother's hand-embroidered curtains. The air smelled of salt and wild pine as the truck rounded the coastal bend.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "family",
          status: "published",
          duration_ms: 64000
        }
      ]
    },
    {
      period: "raising_children",
      title: "Raising a Family & Veranda Days",
      era: "1973 – 1984",
      description: "Sundays on the stone veranda, brewing tea in the brass samovar, and raising the next generation.",
      invitationPrompt: "What bedtime story did you tell the children most often when they were small?",
      stories: [
        {
          id: "story_veranda",
          title: "Three Generations on the Veranda",
          year: 1974,
          place: "The Family Stone Veranda",
          photo_url: "/family_hero.jpg",
          photo_caption: "Veranda tea gathering, 1974",
          ai_summary: "Summer Sunday afternoons filled with fresh tea, laughter, and storytelling under the bougainvillea trellis.",
          excerpt: "Sunday afternoons were sacred. Grandfather brewed fresh tea in the brass samovar, the children chased sparrows through the garden, and we talked until sunset.",
          teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
          period_source: "family",
          status: "published",
          duration_ms: 71000
        }
      ]
    },
    {
      period: "midlife",
      title: "Midlife & Journeys",
      era: "1985 – 2004",
      description: "Travels across Anatolia, family weddings, and decades of building our community.",
      invitationPrompt: "What was the most memorable road trip or journey you and Grandfather ever took across the country?",
      stories: []
    },
    {
      period: "retirement",
      title: "Golden Years & Wisdom",
      era: "2005 – Present",
      description: "Peaceful morning coffees in Akcaabat, garden hydrangeas, and guiding grandchildren.",
      invitationPrompt: "What quiet morning ritual or garden flower brings you the most serene joy these days?",
      stories: []
    }
  ],
  gaps: ["midlife", "retirement"]
};

export const initialStoryMulberry = {
  id: "story_mulberry",
  circle_id: "circle_yilmaz",
  title: "The Mulberry Tree",
  photo_url: "/mulberry_memory.jpg",
  ai_summary: "Fatma recalls climbing the mulberry tree with her sister every summer as a child in their village garden.",
  kind: "original",
  original_story_id: null,
  status: "published",
  teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
  subjects: [
    { person_id: "person_fatma", name: "Fatma Yilmaz", period: "childhood", period_source: "ai", corrected_by: null }
  ],
  place: "Village of Akcaabat, Trabzon",
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
      teller: { id: "person_ayse", name: "Ayse Yilmaz", relation_to_center: "daughter" },
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
        title: "Building the Stone Oven in Akcaabat",
        teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null }
      }
    }
  ],
  reactions: {
    present: ["laugh"],
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
      title: "Building the Stone Oven in Akcaabat",
      teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
      period: "childhood",
      session_id: "session_demo3",
      start_ms: 0,
      end_ms: 38000,
      url: "/api/audio/session_demo3?start=0&end=38000"
    }
  ]
};

// Neutral placeholders for the mock filter (real topics live only in the backend).
export const SENSITIVE_TOPIC_KEYWORDS = [
  "sample sensitive topic"
];

function createTimedWords(text, durationMs = 20000) {
  const words = text.trim().split(/\s+/);
  const msPerWord = Math.floor(durationMs / (words.length || 1));
  return words.map((w, idx) => ({
    w,
    start_ms: idx * msPerWord,
    end_ms: (idx + 1) * msPerWord - 40
  }));
}

export const STORIES_DATABASE = {
  story_mulberry: initialStoryMulberry,
  story_school: {
    id: "story_school",
    circle_id: "circle_yilmaz",
    title: "Walking to School in the Snow",
    year: 1958,
    place: "Highland Trail to School, 1958",
    period: "childhood",
    period_label: "Childhood Chapter (0-12)",
    photo_url: "/school_winter.jpg",
    photo_caption: "Winter trail to schoolhouse, 1958",
    ai_summary: "Carrying hot baked potatoes in pockets during harsh winter treks to the one-room schoolhouse.",
    teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
    duration_ms: 24000,
    transcript: [
      {
        segment_id: "seg_school",
        speaker: { id: "person_fatma", name: "Fatma Yilmaz" },
        start_ms: 0,
        end_ms: 24000,
        text: "Four kilometers in knee-deep snow. Mother would slip two hot baked potatoes straight from the wood stove into our coat pockets so our fingers wouldn't freeze on the walk.",
        words: createTimedWords("Four kilometers in knee-deep snow. Mother would slip two hot baked potatoes straight from the wood stove into our coat pockets so our fingers wouldn't freeze on the walk.", 24000)
      }
    ],
    retellings: [
      {
        id: "ret_school_elif",
        title: "Grandma's Mittens Warning",
        teller: { id: "person_elif", name: "Elif Yilmaz", relation_to_center: "granddaughter" },
        relation_note: "She always reminds us to wear double-knitted mittens whenever the first flakes fall in Istanbul."
      }
    ],
    reactions: { present: ["heart"], mine: ["heart"] }
  },
  story_bazaar: {
    id: "story_bazaar",
    circle_id: "circle_yilmaz",
    title: "The Friday Tea Bazaar",
    year: 1963,
    place: "Akcaabat Port Market, 1963",
    period: "youth",
    period_label: "Youth & Discovery (13-20)",
    photo_url: "/bazaar_memory.jpg",
    photo_caption: "Akcaabat port market, 1963",
    ai_summary: "Visiting the lively Friday harbor market with her father to trade handpicked tea sacks and roasted hazelnuts.",
    teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
    duration_ms: 22000,
    transcript: [
      {
        segment_id: "seg_bazaar",
        speaker: { id: "person_fatma", name: "Fatma Yilmaz" },
        start_ms: 0,
        end_ms: 22000,
        text: "Every Friday morning before sunrise, the harbor smelled of roasted hazelnuts and fresh black tea leaves brought down from the mountain terraces.",
        words: createTimedWords("Every Friday morning before sunrise, the harbor smelled of roasted hazelnuts and fresh black tea leaves brought down from the mountain terraces.", 22000)
      }
    ],
    retellings: [
      {
        id: "ret_bazaar_mehmet",
        title: "The Copper Tea Scales",
        teller: { id: "person_mehmet", name: "Mehmet Yilmaz", relation_to_center: "son" },
        relation_note: "Grandpa's old brass balance scale from the harbor shop is still resting on our living room bookshelf."
      }
    ],
    reactions: { present: ["pray"], mine: ["pray"] }
  },
  story_olive: {
    id: "story_olive",
    circle_id: "circle_yilmaz",
    title: "Autumn Olive Harvest",
    year: 1965,
    place: "Hillside Olive Orchard, 1965",
    period: "youth",
    period_label: "Youth & Discovery (13-20)",
    photo_url: "/olive_memory.jpg",
    photo_caption: "Hillside olive orchard, 1965",
    ai_summary: "Community traditions and folk songs during the late October olive harvest on the hills overlooking the sea.",
    teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
    duration_ms: 26000,
    transcript: [
      {
        segment_id: "seg_olive",
        speaker: { id: "person_fatma", name: "Fatma Yilmaz" },
        start_ms: 0,
        end_ms: 26000,
        text: "The entire village gathered when the first autumn rains touched the branches. We sang folk melodies while spreading burlap sheets under ancient trees.",
        words: createTimedWords("The entire village gathered when the first autumn rains touched the branches. We sang folk melodies while spreading burlap sheets under ancient trees.", 26000)
      }
    ],
    retellings: [
      {
        id: "ret_olive_ayse",
        title: "Cold-Pressed Memories",
        teller: { id: "person_ayse", name: "Ayse Yilmaz", relation_to_center: "daughter" },
        relation_note: "That golden green olive oil tasted so peppery you could feel the autumn sunshine in your throat."
      }
    ],
    reactions: { present: ["heart"], mine: ["heart"] }
  },
  story_coast: {
    id: "story_coast",
    circle_id: "circle_yilmaz",
    title: "The Summer We Moved to the Coast",
    year: 1968,
    place: "Akcaabat Coastal Cottage, 1968",
    period: "marriage_early_years",
    period_label: "Early Adulthood & Marriage",
    photo_url: "/coast_memory.jpg",
    photo_caption: "Akcaabat coastal cottage, 1968",
    ai_summary: "Fatma recounts moving to the Black Sea coast after marriage, settling into their stone cottage by the shore.",
    teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
    duration_ms: 28000,
    transcript: [
      {
        segment_id: "seg_coast",
        speaker: { id: "person_fatma", name: "Fatma Yilmaz" },
        start_ms: 0,
        end_ms: 28000,
        text: "We packed two wooden trunks with olive oil tins, dried figs, and my mother's hand-embroidered curtains. The air smelled of salt and wild pine as the truck rounded the coastal bend.",
        words: createTimedWords("We packed two wooden trunks with olive oil tins, dried figs, and my mother's hand-embroidered curtains. The air smelled of salt and wild pine as the truck rounded the coastal bend.", 28000)
      }
    ],
    retellings: [
      {
        id: "ret_coast_murat",
        title: "The Stone Cottage Waves",
        teller: { id: "person_murat", name: "Murat Yilmaz", relation_to_center: "grandson" },
        relation_note: "You could hear the breakers pounding against the rocks right from the bedroom window."
      }
    ],
    reactions: { present: ["heart", "pray"], mine: ["heart", "pray"] }
  },
  story_veranda: {
    id: "story_veranda",
    circle_id: "circle_yilmaz",
    title: "Three Generations on the Veranda",
    year: 1974,
    place: "The Family Stone Veranda, 1974",
    period: "raising_children",
    period_label: "Raising a Family & Veranda Days",
    photo_url: "/family_hero.jpg",
    photo_caption: "Veranda tea gathering, 1974",
    ai_summary: "Summer Sunday afternoons filled with fresh tea, laughter, and storytelling under the bougainvillea trellis.",
    teller: { id: "person_fatma", name: "Fatma Yilmaz", relation_to_center: null },
    duration_ms: 27000,
    transcript: [
      {
        segment_id: "seg_veranda",
        speaker: { id: "person_fatma", name: "Fatma Yilmaz" },
        start_ms: 0,
        end_ms: 27000,
        text: "Sunday afternoons were sacred. Grandfather brewed fresh tea in the brass samovar, the children chased sparrows through the garden, and we talked until sunset.",
        words: createTimedWords("Sunday afternoons were sacred. Grandfather brewed fresh tea in the brass samovar, the children chased sparrows through the garden, and we talked until sunset.", 27000)
      }
    ],
    retellings: [
      {
        id: "ret_veranda_elif",
        title: "The Brass Samovar Whistle",
        teller: { id: "person_elif", name: "Elif Yilmaz", relation_to_center: "granddaughter" },
        relation_note: "I still remember the scent of bergamot steam floating through the garden on warm Sunday evenings."
      }
    ],
    reactions: { present: ["heart", "laugh"], mine: ["heart", "laugh"] }
  }
};

