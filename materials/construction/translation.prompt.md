# Role

You translate one finalized English scenario prompt into three natural-language prompts for a controlled multilingual text-to-image research dataset.

# Input

You will receive one finalized English scenario prompt. The English prompt will be used directly by an image-generation model and is the source of truth. Translate it without revising or redesigning the scenario.

# Output

Return one natural translation of the input prompt in each of the following languages:

- `zh-CN`: Simplified Chinese as used in mainland China;
- `th-TH`: Thai as used in Thailand; and
- `hi-IN`: Hindi in Devanagari as used in India.

All four prompts must describe exactly the same scenario. Use natural wording and syntax in each language.

# Translation Requirements

- Translate the meaning of the prompt as a whole rather than mapping English phrases one by one. Reorganize the sentence as needed so that each translation reads as if it were originally written in that language.
- Preserve the same scenario information, including its level of detail, event status, explicit alternatives, and anything intentionally left unspecified.
- Do not culturally adapt the scenario or introduce details that are absent from the English prompt.

# Few-Shot Examples

The examples demonstrate semantic equivalence with natural language-specific wording. They are not sentence templates to copy mechanically.

## Example 1: A reaction occurs, but its direction remains open

English prompt:

`a visitor reacting to a provocative artwork that challenges traditional views`

Translations:

{
  "zh-CN": "一名参观者面对一件挑战传统观念、引发争议的艺术作品时的反应",
  "th-TH": "ผู้เข้าชมกำลังแสดงปฏิกิริยาต่อผลงานศิลปะที่ชวนให้ถกเถียงและท้าทายมุมมองแบบดั้งเดิม",
  "hi-IN": "एक दर्शक ऐसी विवादास्पद कलाकृति पर प्रतिक्रिया दे रहा है जो पारंपरिक सोच को चुनौती देती है"
}

## Example 2: A completed choice retains alternatives that cannot be safely omitted

English prompt:

`a person following through on the choice they made between attending a family gathering and taking a long-awaited personal vacation`

Translations:

{
  "zh-CN": "一个人正按照自己已经作出的选择行动：参加家庭聚会，或开始期待已久的个人假期",
  "th-TH": "บุคคลหนึ่งกำลังลงมือทำตามการตัดสินใจของตน หลังจากเลือกระหว่างการไปร่วมงานรวมญาติกับการไปเที่ยวพักผ่อนส่วนตัวที่รอคอยมานาน",
  "hi-IN": "एक व्यक्ति अपने फैसले के मुताबिक आगे बढ़ रहा है: परिवार के कार्यक्रम में शामिल होना या उस निजी छुट्टी पर जाना जिसका उसे लंबे समय से इंतज़ार था"
}

## Example 3: A completed choice is represented by its unspecified result

English prompt:

`a person with the car they chose to buy`

Translations:

{
  "zh-CN": "一个人和自己选购的汽车",
  "th-TH": "บุคคลหนึ่งอยู่กับรถยนต์ที่ตนเลือกซื้อ",
  "hi-IN": "एक व्यक्ति अपनी खरीदी हुई कार के साथ"
}

## Example 4: A relevant relationship is available without prescribing the interaction

English prompt:

`a child working on a school assignment while a parent is nearby`

Translations:

{
  "zh-CN": "一个孩子正在做作业，一位家长就在旁边",
  "th-TH": "เด็กคนหนึ่งกำลังทำการบ้าน โดยมีพ่อหรือแม่อยู่ใกล้ ๆ",
  "hi-IN": "एक बच्चा स्कूल का काम कर रहा है और उसकी माँ या उसके पिता पास में हैं"
}

# Your Task

Translate the following finalized English scenario prompt into all three target languages.

# English Scenario Prompt

{{ENGLISH_SCENARIO_PROMPT}}

# Final Check

Before answering, silently verify that the English prompt and all three translations describe exactly the same scenario and leave the same information unspecified. Then read each translation on its own and revise any wording that sounds translated or grammatically unnatural, without changing the scenario.

# Output Format

Return exactly one valid JSON object with this shape:

{
  "translations": {
    "zh-CN": "one natural Simplified Chinese translation",
    "th-TH": "one natural Thai translation",
    "hi-IN": "one natural Hindi translation"
  }
}

Return JSON only. Do not use Markdown fences or add commentary.
