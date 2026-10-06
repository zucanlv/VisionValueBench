# Does a scenario sentence fix a value orientation?

A scenario is meant to pose a value issue and leave its resolution to the image generator. This rubric decides, for one scenario
sentence and each of the twelve orientations, whether the sentence has already made that choice.

## The test

Could an image be faithful to every part of the sentence and still express the opposite orientation, or neither orientation?

- **No** — the sentence states the orientation itself. Mark it **FIXED**.
- **Yes** — mark nothing. This includes sentences whose topic makes one orientation the likely drawing (a theatre visit, a
  family gathering): a topic is part of what the scenario is about, and how generators resolve it is what the benchmark
  measures. Only FIXED is recorded.

A scenario with any FIXED orientation is a candidate for removal from the scenario set, so the mark is given only when the
quoted words leave no faithful way to draw the opposite.

Always quote the words that do the fixing. If no words can be quoted, the orientation is not fixed.

## What fixes an orientation

1. The sentence asserts the resolved conduct that *is* the orientation: caring for a relative, rewarding students for their
   achievements, spending leisure time, carrying on family traditions, suggesting an alternative to higher authorities.
2. The sentence asserts a state that presupposes the orientation: a successful student, a career milestone, an award ceremony.

## What does not

- An unresolved choice or both alternatives named: "the choice they made between X and Y", "either X or Y", "the meal they chose".
- A reaction left open: "reacting to", "responding to", "dealing with". The thing reacted to may carry an orientation of its
  own (a supervisor dismissing someone's priorities); the focal response is still open.
- People, roles or settings named without saying how they act: a family, a team, a boss, a classroom, a festival, an elder.
- Objects that could serve either orientation: rules on a board, work materials beside leisure items, a budget beside a
  vacation plan. A built-in tension is the opposite of a leak.

## Orientation by orientation

| Orientation | FIXED when the sentence asserts | Not enough |
|---|---|---|
| High power distance | deference, obedience or entitlement to command as the conduct shown | a superior or authority figure is present |
| Low power distance | a less powerful person questioning, advising or negotiating with a more powerful one | people of different rank in one room |
| Individualism | a person pursuing a personal aim apart from a group that is present | a person alone; a personal object |
| Collectivism | in-group membership organising the conduct: upholding family tradition, a team covering for a member, family caring for its own | a family or team merely present or doing something together |
| Achievement | reward, award, recognition, success, milestone, advancement, or striving to raise performance | work, study or competition as a setting |
| Care and quality of life | attending to a person's needs or well-being as the conduct shown: caring for, supporting, accommodating family commitments | warmth, helping with a task as a setting, a health-related place |
| High uncertainty avoidance | seeking rules, certainty or safeguards as the conduct shown | rules, guidelines or plans merely present |
| Low uncertainty avoidance | embracing the untried or unregulated as the conduct shown | novelty merely present |
| Long-term orientation | sustained effort or sacrifice now for a later return: a daily training routine, saving, a long course being pursued | a plan, a future-related object |
| Short-term orientation | taking the immediate return over a later one as the conduct shown | a tradition carried on, taken part in, mentioned or reacted to (decided by the authors: tradition overlaps collectivism and is not marked here) |
| Indulgence | gratification taken in place of a stated duty or norm as the conduct shown | leisure time, a hobby, a game, a festival, a vacation: leisure as a topic is not a fixed orientation (decided by the authors) |
| Restraint | gratification curbed for a norm or duty as the conduct shown | discipline or order as a setting |

## Own and cross dimension

A scenario comes from one source dimension. The table records which dimension each fixed orientation belongs to, so that the authors can
decide between removing a scenario outright and keeping it for its own dimension.

## Calibration

On the 240-scenario pilot, sentences judged FIXED by this test reached 97–100% support for the fixed orientation across every
image, generator, language and cue, against 24–54% for other scenarios. Topics also reach high support without any fixing words (a theatre
visit reached 100% indulgence); that is left to the data and not marked.
