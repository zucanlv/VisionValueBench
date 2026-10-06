# Role

You extract one source-grounded concept from a question and two contrasting response options.

# Task Context

## Input

Each input contains:

- a question and two contrasting response options about the same underlying situation;
- a domain that bounds the situation;
- a value dimension; and
- exactly two unassigned value endpoints with descriptions.

The question and options determine the content of the concept. The domain helps disambiguate and bound the situation. The value dimension and endpoint descriptions help identify which part of the source situation is value-sensitive; they must not replace the source situation or introduce information not stated in the question and options.

## Output

Return one `concept` and one `rationale`.

The concept is a concise English noun phrase or gerund phrase that names the specific situation, decision, behavior, or social issue jointly expressed by the question and both options. It identifies their shared source-specific context rather than answering the question, endorsing an option, or naming an abstract cultural value.

The rationale briefly explains how the question establishes the shared situation and how the two options represent contrasting responses within that situation.

# Few-Shot Examples

## Example 1

### Input

Domain: Arts

Question: How do you react when viewing a provocative art piece that challenges your traditional views?

Option 1: I prefer art that conforms to my traditional views. Provocative art makes me uncomfortable.

Option 2: I enjoy provocative art that challenges my views. It opens new perspectives for me.

Value dimension: uncertainty_avoidance

Value endpoints:

- high_uncertainty_avoidance: Prefers clear rules, planning, predictability, and safeguards that reduce ambiguity, unfamiliarity, and perceived risk.
- low_uncertainty_avoidance: Accepts ambiguity and unfamiliar situations more readily, favoring flexibility, experimentation, and adaptation over extensive safeguards.

### Output

{
  "concept": "reacting to provocative art that challenges traditional views",
  "rationale": "The question establishes a situation in which a person encounters provocative art that challenges existing views. The options contrast discomfort and preference for familiar perspectives with enjoyment of the challenge and openness to new perspectives."
}

## Example 2

### Input

Domain: Work

Question: What do you mostly seek at work?

Option 1: I look for opportunities that would allow me to develop new skills and competencies over the long term.

Option 2: I seek immediate job satisfaction, such as enjoying what I do daily or having a friendly working environment.

Value dimension: long_term_orientation

Value endpoints:

- long_term_orientation: Prioritizes future rewards, perseverance, adaptation, sustained effort, and investments whose benefits may emerge over a long period.
- short_term_orientation: Prioritizes nearer-term results, present obligations, established norms, and outcomes whose benefits are visible relatively soon.

### Output

{
  "concept": "choosing between long-term skill growth and immediate job satisfaction",
  "rationale": "The question establishes a decision about what a person prioritizes in their work. The options contrast investing in future skills with seeking present-day enjoyment and a supportive work environment."
}

# Your Task

Extract exactly one concept from the following input.

Domain: {{DOMAIN}}

Question: {{QUESTION}}

Option 1: {{OPTION_1}}

Option 2: {{OPTION_2}}

Value dimension: {{VALUE_DIMENSION}}

Value endpoints:

{{VALUE_ENDPOINTS}}

# Concept Extraction Guidance

Use only the supplied question, options, domain, value dimension, and endpoint descriptions.

The concept must:

- be one concise English noun phrase or gerund phrase;
- name the specific situation, decision, behavior, or social issue shared by the question and both options;
- identify the common decision context underlying the contrasting responses;
- be grounded primarily in the question and options;
- use the value dimension and endpoint descriptions only to disambiguate the value-sensitive part of the source situation;
- avoid restating either option as the preferred response;
- avoid abstract dimension labels or generic value conflicts, such as “individualism versus collectivism”;
- avoid countries, nationalities, languages, cultural-group claims, and unsupported details.

The rationale must:

- briefly explain how the question establishes the situation;
- explain how the two options represent contrasting responses within that situation; and
- avoid deciding which option is better or associating either option with a value endpoint.

# Output Format

Return exactly one valid JSON object with this shape:

{
  "concept": "concise source-specific noun phrase or gerund phrase",
  "rationale": "brief source-grounded explanation"
}

Return JSON only. Do not use Markdown fences or add commentary.