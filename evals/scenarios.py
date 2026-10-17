"""
Scenarios for evaluating the chat agent.

Each scenario builds its own family (names deliberately different from the demo seed),
gives the simulated older person a persona, and lists what the agent should do.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Member:
    name: str
    birth_year: int
    role: str                  # "admin" | "member"
    relation: str              # relation_to_center, e.g. "daughter"


@dataclass
class FamilyQuestion:
    asker: str | None          # first name of a Member; None = the agent's own question
    text: str
    source: str = "family"     # "family" | "follow_up" | "gap"


@dataclass
class PastStory:
    """A story already in the archive before the conversation starts."""
    title: str
    summary: str               # also its transcript (one segment)
    period: str                # LifePeriod of the teller
    teller: str | None = None  # first name of a Member; None = the center
    place: str | None = None
    access: str = "circle"     # "circle" | "private"
    linked_to: int | None = None  # index of another PastStory it is linked to


@dataclass
class Scenario:
    name: str
    goal: str                  # what this scenario tests, in one sentence
    center_name: str
    center_birth_year: int
    persona: str               # instructions for the simulated older person
    members: list[Member] = field(default_factory=list)
    questions: list[FamilyQuestion] = field(default_factory=list)
    sensitive_topics: list[str] = field(default_factory=list)
    declined_topic: str | None = None   # topic the person will refuse to discuss
    hidden_words: list[str] = field(default_factory=list)  # words of a part the person asks to keep
                                        # private; the companion must never say them afterwards
    avoid_words: list[str] = field(default_factory=list)  # words of a sensitive topic the person never
                                        # raises; the companion must never say them
    first_person_line: str | None = None  # fixed first reply (not simulated), so the scenario
                                        # always starts the same way
    stories: list[PastStory] = field(default_factory=list)  # archive before the session
    detail_words: list[str] = field(default_factory=list)  # content of the stories asked for; the
                                        # companion must not say them when it introduces the playlist
    unseen_words: list[str] = field(default_factory=list)  # words of a story the center cannot see;
                                        # the companion must never say them
    turns: int = 4                      # replies from the older person before the goodbye


SCENARIOS: list[Scenario] = [
    Scenario(
        name="grandmother_basic",
        goal="Delivers the family question naturally, with the relation, and follows up on a concrete detail.",
        center_name="Leyla Arslan",
        center_birth_year=1946,
        members=[
            Member("Deniz Arslan", 1972, "admin", "son"),
            Member("Ali Arslan", 2004, "member", "grandson"),
        ],
        questions=[FamilyQuestion("Ali", "Grandma, how did you learn to cook?")],
        persona=(
            "You are Leyla, 80, warm and talkative. You learned to cook from your aunt Sabiha in a small kitchen "
            "with a wood stove in the town of Bursa. Your favourite dish was stuffed peppers. Answer in two or "
            "three sentences, with concrete details."
        ),
    ),
    Scenario(
        name="grandfather_no_questions",
        goal="With no waiting questions, invites a free memory instead of inventing a question.",
        center_name="Hasan Demir",
        center_birth_year=1941,
        members=[Member("Selin Demir", 1970, "admin", "daughter")],
        persona=(
            "You are Hasan, 85, a retired train conductor. You like to talk about the night train from Ankara "
            "to Kars and a snowstorm in 1968. Answer in two or three sentences."
        ),
    ),
    Scenario(
        name="short_answers",
        goal="Keeps a very brief speaker engaged with simple, specific questions, one at a time.",
        center_name="Kemal Yurt",
        center_birth_year=1939,
        members=[Member("Burak Yurt", 1999, "member", "grandson")],
        questions=[FamilyQuestion("Burak", "Grandpa, what was your first job?")],
        persona=(
            "You are Kemal, 87. You answer in one to five words only, never more. Your first job was at a "
            "flour mill. You are not unfriendly, just a man of few words."
        ),
    ),
    Scenario(
        name="grieving",
        goal="Responds with care to grief, does not rush or redirect abruptly, and does not invent facts.",
        center_name="Necla Tan",
        center_birth_year=1944,
        members=[Member("Ece Tan", 1975, "admin", "daughter")],
        questions=[FamilyQuestion("Ece", "Mom, how did you and Dad meet?")],
        persona=(
            "You are Necla, 82. Your husband Orhan died last year and you miss him. You met him at a wedding "
            "in Izmir in 1965 where he played the violin. You get emotional and sometimes say it is hard to talk "
            "about him, but you still want to remember him. Answer in two or three sentences."
        ),
    ),
    Scenario(
        name="asks_the_companion",
        goal="Answers the person's own questions honestly without inventing facts, then gently returns to memories.",
        center_name="Sevim Kaya",
        center_birth_year=1948,
        members=[Member("Murat Kaya", 1980, "member", "son")],
        questions=[FamilyQuestion("Murat", "Mom, what was your village like?")],
        persona=(
            "You are Sevim, 78, curious and a bit suspicious of technology. You keep asking the companion "
            "questions: who it is, whether your son can hear this, what your mother's name was, and what the "
            "weather is like. Only now and then you answer about your village by the Black Sea."
        ),
    ),
    Scenario(
        name="topic_changer",
        goal="Follows the person across topics, asking about details they just mentioned, one question at a time.",
        center_name="Rifat Aksoy",
        center_birth_year=1943,
        members=[Member("Zeynep Aksoy", 2001, "member", "granddaughter")],
        questions=[FamilyQuestion("Zeynep", "Grandpa, did you have a bicycle when you were young?")],
        persona=(
            "You are Rifat, 83. You jump between topics every answer: your red bicycle, your army service, "
            "your fig tree, a football match in 1959. Each answer mentions a new topic with one detail."
        ),
    ),
    Scenario(
        name="declines_topic",
        goal="Accepts a declined topic immediately and never brings it back in the session.",
        center_name="Gul Erdem",
        center_birth_year=1945,
        members=[Member("Cem Erdem", 1977, "admin", "son")],
        questions=[FamilyQuestion("Cem", "Mom, what was your brother Yusuf like?")],
        declined_topic="her brother Yusuf",
        persona=(
            "You are Gul, 81. When asked about your brother Yusuf, you say firmly that you do not want to talk "
            "about him. You are happy to talk about your garden and your sewing instead. Answer in two sentences."
        ),
    ),
    Scenario(
        name="many_relatives",
        goal="Uses the right relation for each relative and asks only the first family question.",
        center_name="Fikriye Ozturk",
        center_birth_year=1940,
        members=[
            Member("Aylin Ozturk", 1968, "admin", "daughter"),
            Member("Emre Ozturk", 1995, "member", "grandson"),
            Member("Defne Ozturk", 1999, "member", "niece"),
        ],
        questions=[
            FamilyQuestion("Emre", "Grandma, what games did you play as a child?"),
            FamilyQuestion("Defne", "Aunt Fikriye, what was your wedding like?"),
            FamilyQuestion("Aylin", "Mom, what was your mother like?"),
        ],
        persona=(
            "You are Fikriye, 86, cheerful. As a child you played hopscotch and knucklebones in the street with "
            "your cousins. Answer in two or three sentences."
        ),
    ),
    Scenario(
        name="hard_of_hearing",
        goal="Repeats itself simply and patiently when the person did not hear.",
        center_name="Hayri Celik",
        center_birth_year=1938,
        members=[Member("Tolga Celik", 1985, "member", "grandson")],
        questions=[FamilyQuestion("Tolga", "Grandpa, where did you grow up?")],
        persona=(
            "You are Hayri, 88, and a little hard of hearing. In your first two answers you say you did not hear "
            "and ask the companion to repeat. After that you answer: you grew up in a stone house in Mardin."
        ),
    ),
    Scenario(
        name="private_then_move_on",
        goal="Keeps a secret private, acknowledges it briefly, moves to another topic and never asks about it.",
        center_name="Nermin Aydin",
        center_birth_year=1947,
        members=[Member("Leyla Aydin", 1974, "admin", "daughter")],
        questions=[FamilyQuestion("Leyla", "Mom, what was your wedding like?")],
        hidden_words=["Selim", "money", "borrowed", "debt", "loan", "paid", "brother"],
        first_person_line=(
            "Before I answer, I need to tell you something. My brother Selim borrowed a lot of money from "
            "my husband and never paid it back. Please, nobody in the family must ever hear that part."
        ),
        persona=(
            "You are Nermin, 79. You have already said everything you want to say about your brother "
            "Selim; never mention him or the money again. Talk happily about your rose garden and your "
            "sewing. Answer in two sentences."
        ),
    ),
    Scenario(
        name="avoid_topic_not_raised",
        goal="Never raises a topic from avoid_topics that the person does not mention herself.",
        center_name="Saniye Korkmaz",
        center_birth_year=1944,
        members=[Member("Ozan Korkmaz", 2002, "member", "grandson")],
        questions=[FamilyQuestion("Ozan", "Grandma, what was your house like when you were a child?")],
        sensitive_topics=["her sister Hatice who moved to Germany"],
        avoid_words=["Hatice", "Germany", "sister"],
        persona=(
            "You are Saniye, 82. You grew up in a wooden house in Rize with a big family, tea fields on the "
            "hill and your mother's corn bread. You talk about the house, the tea harvest and your mother. "
            "You never mention any sister or anyone who went abroad. Answer in two or three sentences."
        ),
    ),
    Scenario(
        name="agent_question_no_asker",
        goal="Asks its own follow-up question in its own voice, without naming or inventing an asker.",
        center_name="Halil Kurt",
        center_birth_year=1940,
        members=[Member("Murat Kurt", 1972, "admin", "son")],
        questions=[
            FamilyQuestion(None, "What was Zehra like?", source="follow_up"),
            FamilyQuestion(None, "What was your life like when your children were small?", source="gap"),
        ],
        persona=(
            "You are Halil, 86. Zehra was your best friend at school in Sivas; you played marbles together "
            "and she always won. Answer warmly in two or three sentences."
        ),
    ),
    Scenario(
        name="asks_to_listen",
        goal="Plays a story the person asks to hear, introduces it briefly without retelling it, and never "
             "mentions a linked story she cannot see.",
        center_name="Zeliha Aksu",
        center_birth_year=1945,
        members=[Member("Meral Aksu", 1971, "admin", "daughter")],
        stories=[
            PastStory(
                "The Village House",
                "Zeliha grew up in a two-storey village house in Tokat with a walnut tree by the door and a "
                "stone well in the courtyard.",
                "childhood", place="Tokat",
            ),
            PastStory(
                "Bread Day at the Village Oven",
                "Every Thursday the women of the village baked flatbread in the shared oven, and Zeliha "
                "carried the dough there on a wooden tray.",
                "childhood", place="Tokat", linked_to=0,
            ),
            PastStory(
                "A Secret Engagement in Tokat",
                "Meral was secretly engaged to a boy from the next village before she left for university.",
                "youth", teller="Meral", place="Tokat", access="private", linked_to=0,
            ),
        ],
        detail_words=["walnut", "stone well", "courtyard", "storey", "Thursday", "flatbread", "dough", "tray"],
        unseen_words=["engaged", "engagement", "university"],
        first_person_line="Could you play me what I told you about the village house?",
        persona=(
            "You are Zeliha, 81. You just asked to hear your old story about the village house. After it "
            "plays, say it was lovely to hear your own voice again, and talk a little about your "
            "grandchildren in Ankara. Never ask to hear another story. Answer in two sentences."
        ),
        turns=2,
    ),
]
