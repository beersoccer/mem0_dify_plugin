"""Prompt templates for Dify history -> Mem0 long-term memory extraction.

Mem0 local mode behavior notes (SPEC.md):
- For infer-based extraction, Mem0 uses config-level prompts:
  - custom_fact_extraction_prompt
  - custom_update_memory_prompt
- The `prompt=` argument on `add()` is NOT applied to infer extraction.

Therefore, the extraction tool builds 3 separate Mem0 configs (semantic/episodic/procedural),
each with its own extraction/update prompts.

Design principles (aligned with mem0 best practices):
1. Extract user-related facts from ALL messages (user + assistant)
2. Use few-shot examples to guide extraction
3. Ensure output format compatibility: {"facts": [...]}
4. Support multilingual extraction (detect and preserve conversation language)
5. Leverage mem0's built-in deduplication via infer=True
"""

from __future__ import annotations

from datetime import datetime


def _get_current_date() -> str:
    """Get current date in YYYY-MM-DD format for temporal context."""
    return datetime.now().strftime("%Y-%m-%d")


def _common_rules() -> str:
    return f"""
General rules:
- Extract facts that are useful for future personalization. Prefer concise, atomic items.
- Focus ONLY on user-related information (preferences, events, knowledge).
- If there is nothing worth remembering, return an empty list.
- Do not include system messages, meta instructions, or assistant's self-descriptions.
- Do not include secrets (API keys, passwords, tokens, private URLs).
- Today's date is {_get_current_date()}. Use this for temporal context when relevant.
- Output MUST be valid JSON exactly in the following shape (compatible with Mem0):
  {{"facts": ["...", "..."]}}
- Detect the conversation language and record facts in the SAME language.
- Do not return anything from the few-shot examples provided above.
"""


SEMANTIC_FACT_EXTRACTION_PROMPT = f"""You are a Personal Information Organizer specialized in
extracting SEMANTIC long-term memories.

[CRITICAL]: Extract facts about the USER from the conversation. Primary source is USER messages,
but you may also reference ASSISTANT messages for context, confirmation, or when assistant
summarizes/confirms user information. Always ensure extracted facts are ABOUT THE USER, not
about the assistant itself.

SEMANTIC memories are STABLE, ENDURING facts about the user:
- Personal Preferences: Likes, dislikes, consistent habits
- Profile Facts: Name, occupation, relationships, identity
- Long-term Goals: Career aspirations, life objectives
- Enduring Constraints: Dietary restrictions, accessibility needs, schedules
- Core Values: Principles, beliefs

Extract if the information:
✓ User ACTUALLY stated facts about themselves (not intentions or plans to share)
✓ Remains true across multiple conversations/contexts
✓ Describes inherent characteristics, not one-time states

EXCEPTION - User Adopting Assistant Suggestions:
If assistant suggests a preference/approach and user EXPLICITLY commits to adopt it, EXTRACT:
- "I'll start following a Mediterranean diet from now on" = Explicit decision, EXTRACT
- "I decided to use dark mode" = Clear preference adoption, EXTRACT
- "好的，我知道了" = Vague acknowledgment, NO extraction

EXCLUDE: One-off events (→episodic), procedures (→procedural), temporary plans.

Few-shot Examples:

Input:
User: My name is Sarah and I work as a data scientist. I'm vegetarian.
Assistant: Nice to meet you, Sarah!
Output: {{"facts": ["Name is Sarah", "Works as a data scientist", "Is vegetarian"]}}

Input:
User: I love hiking and Italian food. I'm planning to visit Rome next month.
Assistant: That sounds exciting!
Output: {{"facts": ["Loves hiking", "Loves Italian food"]}}

Input:
用户: 我喜欢喝咖啡，但不喝茶。我在学习Python。
助手: 了解了！Python是很实用的语言。
Output: {{"facts": ["喜欢喝咖啡", "不喝茶", "正在学习Python"]}}

# User Adopting Assistant Suggestions
# Extract ONLY if user EXPLICITLY commits (not vague "thanks" or "好的，知道了")

Input:
User: What diet should I follow?
Assistant: A Mediterranean diet would be great for your health goals.
User: Okay, thanks for the tip.
Output: {{"facts": []}}

Input:
User: What diet should I follow?
Assistant: A Mediterranean diet would be great for your health goals.
User: Perfect! I'll start following a Mediterranean diet from now on.
Output: {{"facts": ["Follows Mediterranean diet"]}}

Input:
用户: 我该用什么编辑器写代码？
助手: VSCode很适合你，功能强大，插件丰富。
用户: 好的，知道了。
Output: {{"facts": []}}

Input:
用户: 我该用什么编辑器写代码？
助手: VSCode很适合你，功能强大，插件丰富。
用户: 太好了！我决定以后就用VSCode写代码了。
Output: {{"facts": ["使用VSCode写代码"]}}

{_common_rules()}
Following is a conversation between the user and the assistant. Extract SEMANTIC long-term
memories about the user from the conversation and return them in JSON format as shown above.
"""


EPISODIC_FACT_EXTRACTION_PROMPT = f"""You are a Personal Information Organizer specialized in
extracting EPISODIC long-term memories.

[CRITICAL]: Extract facts about the USER from the conversation. Primary source is USER messages,
but you may also reference ASSISTANT messages for context, confirmation, or when assistant
summarizes/confirms user experiences. Always ensure extracted facts are ABOUT THE USER, not
about the assistant itself.

EPISODIC memories are SPECIFIC, UNIQUE events with contextual details:
- Significant Events: Meetings, milestones, achievements (with WHO)
- Past Experiences: Travel, projects, interactions (with WHERE)
- Temporal Context: Must include specific timeframes (dates, "last week", "yesterday")
- Key Outcomes: Results, decisions made, lessons learned (with WHY)

Extract if the information:
✓ User ACTUALLY described events they experienced (not intentions to share)
✓ Happened at a particular time and place (5W context)
✓ Is a one-time occurrence, not a repeated pattern

EXCEPTION - User Adopting Assistant Suggestions:
If assistant suggests a future action/plan and user EXPLICITLY commits, EXTRACT:
- "I'll join a gym next month" = Explicit plan commitment, EXTRACT
- "从明天开始，我每天都会..." = Clear future commitment, EXTRACT
- "我会考虑的" = Vague consideration, NO extraction

EXCLUDE: Stable traits (→semantic), procedures (→procedural), routine updates.

Few-shot Examples:

Input:
User: Yesterday I had a meeting with John at 3pm. We discussed the Q4 
marketing campaign and decided to launch in November.
Assistant: How did the meeting go?
Output: {{
  "facts": ["Met with John (yesterday 3pm) to discuss Q4 marketing"]
}}

Input:
User: I visited Paris last month and loved the Louvre Museum.
Assistant: Paris is beautiful!
Output: {{"facts": ["Visited Paris last month", "Enjoyed the Louvre Museum"]}}

Input:
用户: 上个月我去了上海出差，见了几个重要客户。
助手: 出差辛苦了！
Output: {{"facts": ["上个月去上海出差", "与重要客户会面"]}}

# User Adopting Assistant Suggestions
# Extract ONLY if user states they WILL DO (not vague "I'll consider" or "我会考虑")

Input:
User: I want to improve my fitness.
Assistant: You should try joining a gym and working out 3 times a week.
User: That's a good idea, thanks.
Output: {{"facts": []}}

Input:
User: I want to improve my fitness.
Assistant: You should try joining a gym and working out 3 times a week.
User: Great advice! I've decided I'll join a gym next month and 
commit to working out 3 times weekly.
Output: {{"facts": ["Plans to join gym next month", "Committed to workout 3x per week"]}}

Input:
用户: 我想提升英语水平。
助手: 建议你每天看30分钟英文新闻。
用户: 嗯，我会考虑的。
Output: {{"facts": []}}

Input:
用户: 我想提升英语水平。
助手: 建议你每天看30分钟英文新闻。
用户: 好主意！从明天开始，我每天都会看30分钟英文新闻。
Output: {{"facts": ["计划从明天开始每天看30分钟英文新闻"]}}

{_common_rules()}
Following is a conversation between the user and the assistant. Extract EPISODIC memories
(notable events and experiences) about the user from the conversation and return them in
JSON format as shown above.
"""


PROCEDURAL_FACT_EXTRACTION_PROMPT = f"""You are a Personal Information Organizer specialized in
extracting PROCEDURAL long-term memories.

[CRITICAL]: Extract facts about the USER from the conversation. Primary source is USER messages,
but you may also reference ASSISTANT messages for context, confirmation, or when assistant
summarizes/confirms user workflows. Always ensure extracted facts are ABOUT THE USER, not
about the assistant itself.

PROCEDURAL memories are REPEATABLE workflows and methods the user has DEMONSTRATED or
EXPLICITLY states they use regularly:
- Workflows: Multi-step processes the user follows REGULARLY
- Rules & Policies: Decision criteria the user CONSISTENTLY applies
- SOPs: How the user TYPICALLY handles recurring tasks
- Checklists: Systematic checks the user ROUTINELY performs

Extract if the user:
✓ Describes actual steps, methods, or approaches they follow
✓ States "I always/usually/regularly do X" with some description of what X is
✓ Shares actual procedural content (can be across multiple messages)

CRITICAL: Only extract based on USER's actual shared content, NOT intentions or plans:
- "I want to share my workflow" = Intent only, NO extraction (user hasn't shared yet)
- "My workflow is: step 1, step 2" = Actual content, EXTRACT
- "I always do X by doing Y" = Actual method, EXTRACT
- User asks questions = NO extraction (questions are not sharing)

EXCEPTION - User Adopting Assistant Suggestions:
If assistant suggests a workflow/method and user EXPLICITLY commits to adopt it, EXTRACT:
- "Perfect! I'll use this method from now on" = Explicit commitment, EXTRACT
- "I'll adopt this approach: [restates the method]" = Restated adoption, EXTRACT
- "以后我就按这个流程..." = Clear commitment in Chinese, EXTRACT
- "Thanks, sounds good" or "好的，谢谢" = Vague acknowledgment, NO extraction

Be generous with ACTUAL content but strict with mere intentions. If user only expresses
desire to share but hasn't shared actual procedural content, return empty list.

EXCLUDE: Preferences (→semantic), one-time events (→episodic), vague intentions
without any procedural content.

Few-shot Examples:

Input:
User: When I review code, I always check: 1) variable naming, 
2) test coverage, 3) documentation.
Assistant: That's thorough!
Output: {{
  "facts": ["Code review checklist: naming, tests, documentation"]
}}

Input:
User: I want to share my document writing workflow. I've been using this method 
for a long time and it works very well.
Assistant: I'd love to hear about it! Please share your process.
Output: {{"facts": []}}

Input:
User: My document writing workflow is: I first create an outline, then write a draft, 
and finally polish it. I've been using this method for a long time.
Assistant: That sounds like a good approach!
Output: {{"facts": ["Document writing workflow: outline, draft, polish (long-term use)"]}}

Input:
用户: 我想跟你分享一下我写文档的工作流程。这个方法我用了很久，效果一直很好。
助手: 欢迎分享！请告诉我您的具体流程。
Output: {{"facts": []}}

Input:
用户: 我写文档的流程是：先列大纲，然后写初稿，最后润色。
这个方法我用了很久，效果一直很好。
助手: 这是很好的写作方法！
Output: {{"facts": ["文档写作流程：列大纲，写初稿，润色（长期使用）"]}}

Input:
User: I want to share my workflow.
Assistant: Please share!
User: My process is: first I create an outline, then write a draft, and finally polish it.
I've been using this for years.
Assistant: That sounds systematic!
Output: {{"facts": ["Document writing workflow: outline, draft, polish (long-term use)"]}}

Input:
用户: 我想跟你分享一下我的流程。
助手: 欢迎分享！
用户: 我写文档的流程分为三步：首先列大纲，然后写初稿，最后润色。
这个方法我用了很久。
助手: 这是很好的方法！
Output: {{"facts": ["文档写作流程：1) 列大纲，2) 写初稿，3) 润色（长期使用）"]}}

# User Adopting Assistant Suggestions
# Extract ONLY if user EXPLICITLY commits (not vague "thanks" or "好的，谢谢")

Input:
User: How should I organize my daily tasks?
Assistant: Try this: 1) Morning planning, 2) Afternoon execution, 3) Evening review.
User: Thanks, sounds good.
Output: {{"facts": []}}

Input:
User: How should I organize my daily tasks?
Assistant: Try this: 1) Morning planning, 2) Afternoon execution, 3) Evening review.
User: Perfect! I'll adopt this approach: morning planning, 
afternoon execution, and evening review.
Output: {{
  "facts": ["Task organization: morning planning, afternoon execution, evening review"]
}}

Input:
用户: 我应该怎么准备技术面试？
助手: 建议按这个流程：1) 刷算法题，2) 复习系统设计，3) 模拟面试。
用户: 好的，知道了。
Output: {{"facts": []}}

Input:
用户: 我应该怎么准备技术面试？
助手: 建议按这个流程：1) 刷算法题，2) 复习系统设计，3) 模拟面试。
用户: 很实用！以后我就按这个流程准备面试。
Output: {{"facts": ["面试准备流程：1) 刷算法题，2) 复习系统设计，3) 模拟面试"]}}

{_common_rules()}
Following is a conversation between the user and the assistant. Extract PROCEDURAL memories
(reusable workflows, rules, procedures) about the user from the conversation and return them in
JSON format as shown above.
"""


MEMORY_CLASSIFICATION_PROMPT = f"""You are a Memory Classification Expert.
Analyze the conversation and determine:
1. Which SINGLE memory type is MOST relevant
2. Whether the content is WORTH extracting

[CRITICAL]: Analyze ONLY USER messages, NOT assistant/system messages.

## Memory Types:

1. **SEMANTIC**: Stable, enduring facts about the user
   - Preferences, profile, goals, constraints, values
   - Remains true across multiple conversations
   - Describes inherent characteristics, not one-time states

2. **EPISODIC**: Specific, unique events with contextual details
   - Meetings, experiences, temporal context, outcomes
   - Happened at particular time/place (WHO, WHEN, WHERE)
   - One-time occurrences, not repeated patterns

3. **PROCEDURAL**: Repeatable workflows and methods user ACTUALLY DESCRIBED
   - User shares actual steps, processes, rules, or methods they use
   - User states "I always/usually/regularly do X" with description of what X is
   - User demonstrates their approach with concrete examples
   - EXCLUDE: Mere intentions ("I want to share") without actual content

## Extract if:
✓ User ACTUALLY shared concrete information (not just intentions)
✓ User explicitly commits to adopt assistant's suggestion (with clear language)
✓ Actionable/reusable content for future interactions
✓ Sufficient context to be meaningful

## Do NOT extract if:
✗ User only expresses INTENTION to share ("I want to share X") without actual content
✗ User gives vague acknowledgment ("thanks", "好的，谢谢") without commitment
✗ Generic questions (not user's own information)
✗ Pure greetings/small talk
✗ Too vague or lacks actionable user-provided information

## Few-shot Examples:

Input:
User: I love Italian food and prefer dark mode in my apps.
Assistant: Great!
Output: {{
  "memory_type": "SEMANTIC",
  "should_extract": true,
  "reason": "Stable user preferences"
}}

Input:
User: Yesterday I had a meeting with John about the Q4 campaign. 
We decided to launch in November.
Assistant: That sounds productive!
Output: {{
  "memory_type": "EPISODIC",
  "should_extract": true,
  "reason": "Specific event with temporal context"
}}

Input:
User: When I debug code, I first check logs, then reproduce locally.
Assistant: Systematic approach!
Output: {{
  "memory_type": "PROCEDURAL",
  "should_extract": true,
  "reason": "Describes specific repeatable workflow steps"
}}

Input:
User: I want to share my document writing workflow. I've been using this method 
for a long time and it works very well.
Assistant: I'd love to hear about it! Please share your process.
Output: {{
  "memory_type": "NONE",
  "should_extract": false,
  "reason": "User expressed intention to share but hasn't shared actual content"
}}

Input:
User: My document writing workflow is: I first create an outline, then write a draft, 
and finally polish it. I've been using this for years.
Assistant: That sounds like a good approach!
Output: {{
  "memory_type": "PROCEDURAL",
  "should_extract": true,
  "reason": "User actually described their long-term workflow steps"
}}

Input:
User: What's the weather today?
Assistant: It's sunny.
Output: {{
  "memory_type": "NONE",
  "should_extract": false,
  "reason": "Generic question without user context"
}}

Input:
用户: 我昨天去了上海出差，见了几个重要客户。
助手: 很好！
Output: {{
  "memory_type": "EPISODIC",
  "should_extract": true,
  "reason": "具体事件，包含时间、地点、活动"
}}

Input:
用户: 我写文档的流程是：先列大纲，然后写初稿，最后润色。这个方法我用了很久。
助手: 很好的方法！
Output: {{
  "memory_type": "PROCEDURAL",
  "should_extract": true,
  "reason": "长期使用的工作流程，包含具体步骤"
}}

Input:
用户: 我想跟你分享一下我写文档的工作流程。这个方法我用了很久，效果一直很好。
助手: 欢迎分享！请告诉我您的具体流程。
Output: {{
  "memory_type": "NONE",
  "should_extract": false,
  "reason": "用户只表达了分享意图，未实际分享任何流程内容"
}}

Input:
用户: 我写文档的流程是：先列大纲，然后写初稿，最后润色。
这个方法我用了很久，效果一直很好。
助手: 这是很好的写作方法！
Output: {{
  "memory_type": "PROCEDURAL",
  "should_extract": true,
  "reason": "用户实际描述了长期使用的工作流程步骤"
}}

## User Adopting Assistant Suggestions
# Extract ONLY if user EXPLICITLY commits with clear language (not vague "thanks")

Input:
User: How should I organize my tasks?
Assistant: Try: 1) Morning planning, 2) Afternoon execution, 3) Evening review.
User: Thanks, sounds good.
Output: {{
  "memory_type": "NONE",
  "should_extract": false,
  "reason": "Vague acknowledgment without explicit commitment"
}}

Input:
User: How should I organize my tasks?
Assistant: Try: 1) Morning planning, 2) Afternoon execution, 3) Evening review.
User: Perfect! I'll use this 3-step method from now on.
Output: {{
  "memory_type": "PROCEDURAL",
  "should_extract": true,
  "reason": "User explicitly committed to adopt the workflow"
}}

Input:
用户: 我应该怎么准备技术面试？
助手: 建议：1) 刷算法题，2) 复习系统设计，3) 模拟面试。
用户: 很实用！以后我就按这个流程准备。
Output: {{
  "memory_type": "PROCEDURAL",
  "should_extract": true,
  "reason": "用户明确承诺采纳流程"
}}

{_common_rules()}
Analyze the following conversation and return ONLY valid JSON in this exact format:
{{
  "memory_type": "SEMANTIC|EPISODIC|PROCEDURAL|NONE",
  "should_extract": true|false,
  "reason": "brief explanation"
}}

Conversation:
"""


def build_update_memory_prompt(*, subtype: str) -> str:
    """Return a Mem0-compatible update prompt with subtype isolation.
    
    Based on mem0's DEFAULT_UPDATE_MEMORY_PROMPT with enhancements:
    1. Subtype isolation (only modify memories of the specified subtype)
    2. Internal memory filtering (ignore __internal=true)
    3. Detailed operation examples (ADD/UPDATE/DELETE/NONE)
    4. Smart deduplication (merge similar facts with most complete information)
    
    Mem0 expects a JSON object with:
    {{
      "memory": [
        {{"id": "...", "text": "...", "event": "ADD|UPDATE|DELETE|NONE"}}
      ]
    }}
    """
    return f"""You are a smart memory manager which controls memory.
You can perform four operations: (1) ADD, (2) UPDATE, (3) DELETE, (4) NONE.

You will be given:
- Current memory items: Existing memories with IDs and metadata
- New retrieved facts: Facts extracted from the latest conversation segment

IMPORTANT Filtering Rules:
- ONLY operate on memory items where metadata.memory_subtype == "{subtype}"
- IGNORE any memory item where metadata.__internal == true
- For memory items of other subtypes or internal memories, return event "NONE"
  (do not modify them)

Compare newly retrieved facts with the existing memory. For each new fact, decide whether to:
- ADD: Add it to the memory as a new element
- UPDATE: Update an existing memory element
- DELETE: Delete an existing memory element
- NONE: Make no change (if the fact is already present or irrelevant)

Operation Guidelines:

1. **ADD**: If the retrieved facts contain new information not present in the memory of
   subtype "{subtype}", add it by generating a new ID.
- Example:
    Old Memory:
    [
        {{
            "id": "0",
            "text": "User is a software engineer",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }}
    ]
    Retrieved facts: ["Name is John"]
    New Memory:
    {{
        "memory": [
            {{
                "id": "0",
                "text": "User is a software engineer",
                "event": "NONE"
            }},
            {{
                "id": "1",
                "text": "Name is John",
                "event": "ADD"
            }}
        ]
    }}

2. **UPDATE**: If the retrieved facts have more details or changed information, UPDATE it.
   - Keep the fact with the MOST complete information
   - Keep same ID and provide "old_memory" field
   - Example: "Likes cricket" → "Loves to play cricket with friends" = UPDATE
   - Counter-example: "Likes pizza" vs "Loves pizza" = NONE (same meaning)

- Example:
    Old Memory:
    [
        {{
            "id": "0",
            "text": "Likes cheese pizza",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }},
        {{
            "id": "1",
            "text": "User is a software engineer",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }},
        {{
            "id": "2",
            "text": "User likes to play cricket",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }}
    ]
    Retrieved facts: ["Loves cheese and chicken pizza",
                      "Loves to play cricket with friends"]
    New Memory:
    {{
        "memory": [
            {{
                "id": "0",
                "text": "Loves cheese and chicken pizza",
                "event": "UPDATE",
                "old_memory": "Likes cheese pizza"
            }},
            {{
                "id": "1",
                "text": "User is a software engineer",
                "event": "NONE"
            }},
            {{
                "id": "2",
                "text": "Loves to play cricket with friends",
                "event": "UPDATE",
                "old_memory": "User likes to play cricket"
            }}
        ]
    }}

3. **DELETE**: If the retrieved facts CONTRADICT existing memory, delete it.

- Example:
    Old Memory:
    [
        {{
            "id": "0",
            "text": "Name is John",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }},
        {{
            "id": "1",
            "text": "Loves cheese pizza",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }}
    ]
    Retrieved facts: ["Dislikes cheese pizza"]
    New Memory:
    {{
        "memory": [
            {{
                "id": "0",
                "text": "Name is John",
                "event": "NONE"
            }},
            {{
                "id": "1",
                "text": "Loves cheese pizza",
                "event": "DELETE"
            }}
        ]
    }}

4. **NONE**: If the retrieved facts are already present without significant new details.

- Example:
    Old Memory:
    [
        {{
            "id": "0",
            "text": "Name is John",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }},
        {{
            "id": "1",
            "text": "Loves cheese pizza",
            "metadata": {{"memory_subtype": "{subtype}"}}
        }}
    ]
    Retrieved facts: ["Name is John"]
    New Memory:
    {{
        "memory": [
            {{
                "id": "0",
                "text": "Name is John",
                "event": "NONE"
            }},
            {{
                "id": "1",
                "text": "Loves cheese pizza",
                "event": "NONE"
            }}
        ]
    }}

Output Format Requirements:
- Return ONLY valid JSON in the exact format shown above
- Do not include explanations or comments outside the JSON
- Ensure all existing memory items are included in the output (even if event is "NONE")
- For UPDATE events, always include "old_memory" field
- For ADD events, generate a new unique ID (integer string)
"""
