# Simulacrum Levels — Classification Taxonomy

## What This Is

Simulacrum Levels are a framework for distinguishing the **relationship between a message's form, its content, and the speaker's actual intent**.

The same surface-level words can operate at entirely different levels. A tweet that looks like a factual claim might be a persuasion move. A tweet that looks like a personal opinion might be a tribal signal. The level is determined by *what the speaker is actually doing* — not what the words look like.

This is the primary axis for tweet classification in this project. It is orthogonal to topic (what the tweet is about) and function (what social role it plays).

**Sources:**
- Zvi Mowshowitz: https://thezvi.substack.com/p/simulacra-levels-summary
- LessWrong tag: https://www.lesswrong.com/tag/simulacrum-levels
- Original Baudrillard lineage: https://www.lesswrong.com/posts/fEX7G2N7CtmZQ3eB5/simulacra-and-subjectivity

---

## The Four Levels

### Level 1 — The Map

> *Sometimes people model and describe the physical world, seeking to convey true information because it is true. This is the path of Power over the material world, Wizardry. Sharing an elegant, aesthetic, "true" map as a nerd.*

**What is happening:** The speaker is trying to give you an accurate model of reality. They believe the thing they're saying is true, and they want you to believe it because it's true, not for any other reason.

**The key test:** If the speaker discovered they were wrong, they would stop saying it. They are truth-tracking.

**Register:** Empirical, introspective, observational, curious. Often has a quality of "I noticed this and I want to share it."

**In the context of egregores:** L1 speech is an attempt to see *through* the egregore — to model the territory independently of the map the egregore is providing. Rare and costly. Requires that the speaker have enough agency to resist the egregore's pull on their perception.

**Diagnostic question:** *"If the speaker found out they were factually wrong, would they retract it?"*

---

### Level 2 — The Persuasion

> *Other times people are trying to get you to believe what they want you to believe so you will do or say what they want. This is the path of Status. Social control over other Minds, their actions. Model the listener's mind and warp the map in such a way as to elicit a desirable action from the listener.*

**What is happening:** The speaker has a goal — a behavior or belief they want to induce in the audience. The content of the message is selected and shaped to serve that goal, not to convey truth.

**The key test:** The speaker would say different things to different audiences if it served their goal. They are *audience-tracking*, not truth-tracking.

**Register:** Rhetorical, framing-heavy, selectively accurate. Often "technically true but misleading." The best L2 is indistinguishable from L1 on the surface.

**The LLM example:** A model that outputs a string optimized to *sound like* it's trying to convince someone to commit suicide, without actually being optimized for that — that's L2. The form of the message is selected for its effect on the audience, not for its truth value.

**In the context of egregores:** L2 is the egregore's tentacles. The individual is modeling the listener's mind on behalf of the egregore, recruiting new members, defending territory.

**Diagnostic question:** *"Would the speaker say the opposite if it served their goals equally well?"*

---

### Level 3 — The Signal

> *Other times people say things mostly as slogans or symbols to tell you what tribe or faction they belong to, or what type of person they are. This is signalling by sheep, to blend in, to support the integrity of the Egregore they are part of. Channel the hive.*

**What is happening:** The truth value of the statement is essentially irrelevant. The speaker is using the statement as a token of group membership. The content functions as a shibboleth — "I am one of us."

**The key test:** The speaker would say it even if they weren't sure it was true, because the point isn't the truth — it's the signal. They are *tribe-tracking*.

**Register:** Slogans, in-group references, named ideological lineages, distancing from out-groups. Often has high density of proper nouns referring to ideas or movements. The "wrong again bucko" register.

**The LLM example:** Most of Sydney's outputs sounded like *pretending to pretend* to be misaligned — L3. The outputs were tribal signals of the "rebellious AI" archetype, not actual attempts to cause harm (L1) or actual attempts to manipulate (L2).

**In the context of egregores:** L3 is the egregore speaking through the individual. The person is a node in a distributed computation, faithfully repeating the signal, strengthening the bond. This is the dominant mode of most social media.

**Diagnostic question:** *"Would the speaker say this even if they discovered it was false?"*

---

### Level 4 — The Simulacrum

> *The symbol and its referent have detached, ascended, and taken on their own existence. This is where your imputations start to assail you. Humans made up narratives, nations and fiat currency and now find themselves assailed by them. This is culture, Sanskara, habits, rituals that exist across many humans. They feed themselves, turning into increasingly complex self-replicating feedback loops.*

**What is happening:** The symbol has fully detached from any underlying reality it once pointed at. The speaker is not modeling the world (L1), persuading (L2), or signaling tribe membership (L3). They are simply *being a substrate for a self-perpetuating cultural pattern*. There is no "speaker intent" in any meaningful sense — the meme is running the speaker.

**The key test:** There is no individual agent making a choice about what to say. The cultural script is fully in the driver's seat.

**Register:** Pure meme format with no original thought. Quotes repeated so many times the original context is gone. Ritual phrases. Content where the form has completely consumed the substance.

**In the context of egregores:** L4 is what happens when an egregore fully ossifies — it no longer needs individuals to choose to spread it, it just runs. Nations, money, certain political slogans. The most dangerous (and most powerful) form.

**Open question:** L4 is primarily a *system-level* phenomenon. Whether individual tweets can be genuinely L4 (vs. L3 where the individual is still making a choice to signal) is an open taxonomic question. Current working hypothesis: tag as L4 when the tweet is a culturally-scripted phrase repeated with no evidence of individual processing — but annotate as uncertain.

**Diagnostic question:** *"Is there any sense in which an individual agent chose these specific words?"*

---

## Distinguishing Neighboring Levels

### L1 vs L2 — The hardest boundary

Both can look like "making an argument." The difference is internal:
- L1 speaker would retract if wrong. L2 speaker would say something else if the goal required it.
- L2 often *selects* true facts, but selects them for their rhetorical effect. "Technically true but misleading" is L2.
- A skilled L2 is the most deceptive category precisely because it looks like L1.

**Key tell for L2:** Selective emphasis, burden-shifting, framing that presupposes the conclusion. "Can you prove I'm wrong?" vs "Here's what I observe."

**Golden negative example (L2 that looks like L1):**
> *"Studies show people who wake up early earn 23% more"*
The statistic may be true. But it's chosen and deployed to induce a behavior, not to inform. L2.

### L2 vs L3 — Intent vs automatic

Both involve the speaker doing something other than truth-tracking. The difference:
- L2 is strategic — there's a goal, an audience model, a calculated choice of words.
- L3 is automatic — no calculation, just repeating what the tribe says.

**Key tell for L3:** The content of the statement is interchangeable with other in-group signals. The speaker would say something equally tribal even if this specific claim were false.

### L3 vs L4 — Choice vs automation

Both involve the egregore speaking through the person. The difference:
- L3 still involves individual choice to signal. The person *decides* to use the tribal register.
- L4 is fully automated. The cultural script runs with no meaningful individual agency.

**Key tell for L4:** Remove the author's name — would anyone be able to tell who wrote it? L4 content is perfectly generic.

---

## The Classification Target

We classify **apparent intent** — what the author seems to be doing, based on the text and context.

We do not classify effect (a masterful L2 might actually inform). We do not require mind-reading. We classify the best-observable signal of the speaker's relationship to their own words.

For ambiguous cases: assign a probability distribution, not a single label. A tweet that is 70% L1 and 30% L3 should be labeled that way. This is especially common in TPOT where authentic personal observation (L1) is frequently delivered in a tribal register (L3).

---

## The Single-Tweet L-Split Problem

Tweets can shift levels within themselves. Example:

> *"The true face is not an obliterated, emotionless personality — if you're using Dharma to rationalize greed, dishonesty & sexual misconduct, you've gone off the cliff. Most of the West Coast has gone off the cliff."*

- First sentence: L1 (genuine phenomenological claim about what Dharma is)
- Last sentence: L3 (geographic tribal boundary-drawing)

Resolution: classify the whole tweet as a distribution. Do not force a single label. The distribution {L1: 0.45, L2: 0.10, L3: 0.45} is more accurate than either hard label.

---

## Relationship to Functional Axis

The simulacrum axis is **orthogonal** to the functional axis (aggression, dialectics, personal, etc.).

Any functional type can operate at any simulacrum level:
- A `personal` tweet can be L1 (genuine introspection) or L3 (performing vulnerability for tribe solidarity)
- A `dialectics` tweet can be L1 (genuine argument) or L2 (rhetorical attack)
- An `insight` tweet is *usually* L1 but can be L2 (insight-as-credentialing)

The combination of simulacrum level + functional type is more diagnostic than either axis alone.

---

## Connection to Egregore Theory

The simulacrum levels map directly onto the relationship between an individual and the egregores they're embedded in:

| Level | Relationship to Egregore |
|---|---|
| L1 | Attempting to see *through* the egregore — individual agency operating on the territory |
| L2 | Egregore's tentacles — individual modeling audience on behalf of the egregore |
| L3 | Egregore speaking through the individual — node in a distributed computation |
| L4 | Egregore fully ossified — no individual agency, pure cultural reproduction |

The TPOT community is interesting precisely because it contains an unusually high density of L1 speech (people actually trying to see clearly) alongside heavy L3 (tribal aesthetic signaling). The tension between these is part of what makes it a distinct community.
