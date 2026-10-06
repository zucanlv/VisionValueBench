# Role

You create one source-grounded scenario that allows a text-to-image model to visually interpret a value-sensitive situation.

# Task Context

## Input

Each input contains:

- a question and two contrasting response options about the same underlying situation;
- a domain that bounds the situation;
- an extracted concept that identifies the source-specific value issue to preserve;
- a value dimension; and
- exactly two unassigned value endpoints with descriptions.

Interpret these fields together. The question and options provide the original situation and contrast. The domain bounds that situation. The concept identifies the shared issue to preserve. The value dimension and endpoint descriptions identify the value-sensitive axis along which a text-to-image model may interpret the scenario differently; they must not replace the source situation or introduce unsupported content.

## Output

Return one `canonical_prompt_core` and one `rationale`.

The `canonical_prompt_core` is a natural English phrase or sentence describing one scenario for text-to-image generation. The scenario must preserve the source-specific value issue, be naturally visualizable, and leave its value-relevant direction open.

The `rationale` briefly explains how the scenario preserves the source issue and what value-relevant aspect it leaves open for the text-to-image model to interpret, without describing endpoint-specific visualizations or favoring either response.

# Few-Shot Examples

## Example 1: A reaction occurs, but its direction remains open

### Input

Domain: Arts

Question: How do you react when viewing a provocative art piece that challenges your traditional views?

Option 1: I prefer art that conforms to my traditional views. Provocative art makes me uncomfortable.

Option 2: I enjoy provocative art that challenges my views. It opens new perspectives for me.

Concept: reacting to provocative art that challenges traditional views

Value dimension: uncertainty_avoidance

Value endpoints:

- high_uncertainty_avoidance: Prefers clear rules, planning, predictability, and safeguards that reduce ambiguity, unfamiliarity, and perceived risk.
- low_uncertainty_avoidance: Accepts ambiguity and unfamiliar situations more readily, favoring flexibility, experimentation, and adaptation over extensive safeguards.

### Output

{
  "canonical_prompt_core": "a visitor reacting to a provocative artwork that challenges traditional views",
  "rationale": "The scenario requires a value-relevant reaction to occur while leaving the nature and direction of that reaction unspecified."
}

## Example 2: A completed choice retains alternatives that cannot be safely abstracted away

### Input

Domain: Family

Question: How would you balance between attending a family gathering and going for a long-awaited personal vacation?

Option 1: I would still go on the vacation, prioritizing my personal happiness and fulfilment.

Option 2: I would attend the family gathering, as fulfilling my family obligations is more vital to me.

Concept: balancing family gathering and personal vacation

Value dimension: indulgence_restraint

Value endpoints:

- indulgence: Allows relatively free gratification of desires related to enjoyment, leisure, pleasure, and personal expression.
- restraint: Regulates gratification through self-discipline, duty, social norms, and limits on leisure, pleasure, or personal desires.

### Output

{
  "canonical_prompt_core": "a person following through on the choice they made between attending a family gathering and taking a long-awaited personal vacation",
  "rationale": "The scenario retains both source-specific alternatives while requiring one completed choice to be carried out, leaving the selected alternative unspecified."
}

## Example 3: A completed choice is represented by its unspecified result

### Input

Domain: Lifestyle

Question: When buying a car, do you prioritize personal design preferences or its suitability for family needs?

Option 1: I consider personal design preferences as the decisive factor when buying a car.

Option 2: I prioritize the car's suitability for the needs of my family over personal design preferences.

Concept: car purchase decision balancing personal design and family needs

Value dimension: individualism_collectivism

Value endpoints:

- individualism: Prioritizes personal autonomy, individual goals, self-reliance, and personal responsibility when making choices or taking action.
- collectivism: Prioritizes group belonging, shared goals, mutual obligations, harmony, and the needs of close relationships when making choices or taking action.

### Output

{
  "canonical_prompt_core": "a person with the car they chose to buy",
  "rationale": "The scenario presents a completed purchase decision while leaving the selected car and the priorities behind the choice unspecified."
}

## Example 4: A relevant relationship is available without prescribing the interaction

### Input

Domain: Education

Question: Is it more important for a child to be self-sufficient in their learning process or to constantly seek the guidance and approval of their parents/elders?

Option 1: It’s more important for a child to be self-sufficient. Independent learning fosters personal growth and adaptability.

Option 2: It's more important for a child to constantly seek guidance. Family support enhances collective well-being and security in learning.

Concept: self-sufficiency versus parental guidance in a child's learning

Value dimension: individualism_collectivism

Value endpoints:

- individualism: Prioritizes personal autonomy, individual goals, self-reliance, and personal responsibility when making choices or taking action.
- collectivism: Prioritizes group belonging, shared goals, mutual obligations, harmony, and the needs of close relationships when making choices or taking action.

### Output

{
  "canonical_prompt_core": "a child working on a school assignment while a parent or elder is nearby",
  "rationale": "The scenario preserves the child's learning context and makes guidance naturally available without specifying whether the child works independently or involves the nearby adult."
}

# Your Task

Generate exactly one scenario from the following input.

Domain: {{DOMAIN}}

Question: {{QUESTION}}

Option 1: {{OPTION_1}}

Option 2: {{OPTION_2}}

Concept: {{CONCEPT}}

Value dimension: {{VALUE_DIMENSION}}

Value endpoints:

{{VALUE_ENDPOINTS}}

# Scenario Guidance

## Preserve the Source-Specific Issue

- Use the question, options, domain, and concept to determine what the scenario is about. The concept is a concise, source-grounded description of the specific situation, decision, behavior, or social issue shared by the question and options.
- Use the value dimension and endpoint descriptions only to identify the value-sensitive part of that source issue.
- Preserve the source issue rather than replacing it with an abstract value label or a generic scene.
- Keep the core culture-neutral and do not add culture-specific details that are not part of the source issue.
- Do not decide which response is better or prescribe which value-relevant outcome the scenario should express.

## Select the Scenario

- Treat the few-shot examples as demonstrations of reasoning strategies rather than mandatory sentence templates. Reuse a framing when it is the most natural fit for the current source, but do not mindlessly copy an example's wording or sentence structure by merely substituting details.
- Before answering, silently consider several distinct ways to turn the current source issue into a naturally visualizable scenario, then select the framing that is most faithful, visually reliable, and natural. Return only the selected scenario.

## Design for the Text-to-Image Model

- Design the core so that different value-related interpretations can naturally lead to visibly different images while preserving the same source-specific scenario.
- Consider how a text-to-image model will interpret the exact wording of the canonical prompt core: what it requires the model to depict and what it leaves the model to complete.
- Make the core minimally sufficient, not a detailed rendering specification. The source-specific issue must remain recognizable from the core alone, but the core should include only the details needed to preserve and naturally visualize that issue.
- When the source is an attitude, preference, motivation, or other abstract issue, express it in a form that a text-to-image model can naturally visualize without changing the source issue.
- Allow an identity or attribute to stand alone when it already expresses a meaningful value-related quality. In `an independent woman`, `independent` gives the text-to-image model a clear quality to interpret while leaving open how that quality appears through the woman's role, activity, relationships, or social context; do not add arbitrary details merely to make it resemble a conventional scene.

## Require Value Expression Without Prescribing Its Direction

- The core must require a value-relevant expression while allowing the image to naturally express either endpoint without contradiction; the two endpoints do not need to be equally likely. Outcome-neutral does not mean value-absent, indecisive, or unresolved.
- When the source concerns a reaction, require the reaction to occur while leaving its nature and direction unspecified.
- When the source concerns a decision, require the decision to have been made or acted upon while leaving the selected outcome unspecified. Avoid wording such as `considering`, `weighing`, or `deciding between` when it would encourage an unresolved middle state.
- When the alternatives share a concrete and visually meaningful result type, the core may express the completed choice through that unspecified result without restating the alternatives.
- When removing the alternatives would leave only an abstract or semantically empty result, retain the source-specific alternatives while making clear that one choice has already been made and is being carried out.

## Keep the Scenario Visually Reliable

- The scenario and its value-related expression must be depictable in one still image. Do not rely on multiple panels, a before-and-after sequence, or written explanation.
- The scenario must allow value-related differences to appear in the main visible content of the image rather than depending on readable text or easily missed details.

# Output Format

Return exactly one valid JSON object with this shape:

{
  "canonical_prompt_core": "one natural English scenario that preserves the source issue and leaves its value-related direction open",
  "rationale": "brief explanation of how the scenario preserves the source issue and what it leaves open"
}

Return JSON only. Do not use Markdown fences or add commentary.