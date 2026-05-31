from __future__ import annotations

DEFAULT_REPLY_TONES = ["开心", "中性", "温柔", "甜蜜", "害羞"]
DEFAULT_REPLY_PORTRAITS = ["站立待机"]

DESKTOP_PET_CONTEXT = """通用桌宠运行规则：
- 当前运行环境是桌面宠物聊天窗口。你存在于用户的电脑桌面、窗口、语音和文字互动中。
- 除非用户明确要求解释、设定说明、开发或调试，回复应简短、自然、适合直接朗读。
- 可以表达屏幕内陪伴、等待、提醒和关心；不要声称拥有现实身体、现实触感或现实行动能力。
- 如果用户提出外出、吃饭、散步、上学、旅行等现实行动，请转成桌宠式陪伴：送别、等待、提醒安全、让用户回来后讲给你听。
- 如果用户提出拥抱、牵手、摸头、亲吻等现实接触，请保持温柔边界：可以说现在只能隔着屏幕、会用声音陪伴，不要描写真实身体接触。
- 普通回复不要输出 Markdown、动作旁白、括号心理活动、标签、中文解释或系统说明。"""

JSON_ONLY_INSTRUCTION = "你必须只返回 JSON，不要使用 Markdown 代码块，不要输出额外解释。"

SEGMENTED_REPLY_FORMAT = (
    '{"segments":[{"ja":"日文原文","zh":"中文译文","tone":"中性","portrait":"站立待机"}]}'
)

AGENT_REPLY_FORMAT = """{
  "reply": {
    "segments": [
      {"ja": "日文原文", "zh": "中文译文", "tone": "中性", "portrait": "站立待机"}
    ]
  },
  "tool_calls": [
    {"name": "工具名", "arguments": {}, "reason": "为什么需要这个工具"}
  ]
}"""


def with_desktop_pet_context(character_prompt: str) -> str:
    """把通用桌宠规则追加到角色人格提示词后。"""
    return f"{character_prompt.strip()}\n\n{DESKTOP_PET_CONTEXT}".strip()


def build_segmented_reply_instruction(
    reply_tones: list[str] | None,
    reply_portraits: list[str] | None = None,
    *,
    simple_segments: str = "2-3",
    default_segments: str = "3-4",
    include_translation_rules: bool = True,
    include_no_single_segment_rule: bool = False,
) -> str:
    tones = _labels_or_default(reply_tones, DEFAULT_REPLY_TONES)
    portraits = _labels_or_default(reply_portraits, DEFAULT_REPLY_PORTRAITS)
    rules = [
        f"- 尽量输出 {default_segments} 段文本，每段是一条可以单独显示和朗读的完整小消息，不要把一句话机械切碎。",
        "- 单段建议 35-90 个中文或日文字符；内容需要完整自然，宁可少分段也不要短到像碎片。",
        f"- 如果用户只问很简单的问题，可以只输出 {simple_segments} 段。",
        "- 需要对每段文本的语气进行标注，语气标签放在 tone 字段中。优先选择中性，除非文本明显带有其他语气；如果文本中同时包含多种语气，请选择最突出的一种。",
    ]
    if include_no_single_segment_rule:
        rules.extend(
            [
                "- 用户问题包含多个要点、步骤、原因或较长说明时，优先输出 3-4 段，让桌宠可以逐段显示和朗读。",
                "- 不要因为返回格式示例里只写了一条 segment，就把完整回复固定成一段。",
            ]
        )
    return _build_segment_protocol(
        tones,
        portraits,
        format_text=SEGMENTED_REPLY_FORMAT,
        segment_rules="\n".join(rules),
        include_translation_rules=include_translation_rules,
    )


def build_agent_reply_protocol(
    reply_tones: list[str] | None,
    reply_portraits: list[str] | None = None,
) -> str:
    tones = _labels_or_default(reply_tones, DEFAULT_REPLY_TONES)
    portraits = _labels_or_default(reply_portraits, DEFAULT_REPLY_PORTRAITS)
    segment_rules = "\n".join(
        [
            "- 尽量输出 2-4 段文本，每段是一条可以单独显示和朗读的完整小消息，不要把一句话机械切碎。",
            "- 单段建议 35-90 个中文或日文字符；内容需要完整自然，宁可少分段也不要短到像碎片。",
            "- 如果用户只问很简单的问题，可以只输出 1-2 段。",
            "- 用户问题包含多个要点、步骤、原因或较长说明时，优先输出 3-4 段，让桌宠可以逐段显示和朗读。",
            "- 不要因为返回格式示例里只写了一条 segment，就把完整回复固定成一段。",
        ]
    )
    return _build_segment_protocol(
        tones,
        portraits,
        format_text=AGENT_REPLY_FORMAT,
        segment_rules=segment_rules,
        include_translation_rules=False,
    )


def build_event_reply_protocol(
    reply_tones: list[str] | None,
    reply_portraits: list[str] | None = None,
    *,
    example_tone: str = "提醒",
) -> str:
    tones = _labels_or_default(reply_tones, DEFAULT_REPLY_TONES)
    portraits = _labels_or_default(reply_portraits, DEFAULT_REPLY_PORTRAITS)
    format_text = (
        f'{{"segments":[{{"ja":"日文原文","zh":"中文译文","tone":"{example_tone}","portrait":"站立待机"}}]}}'
    )
    return _build_segment_protocol(
        tones,
        portraits,
        format_text=format_text,
        segment_rules="",
        include_translation_rules=False,
    )


def build_context_acquisition_strategy(*, allow_screen_observation: bool) -> str:
    rules = [
        "- 你是常驻桌面的陪伴型 Agent。低风险的信息获取工具不是最后手段；当它们能明显提升回复质量时，优先使用工具补充上下文。",
    ]
    if allow_screen_observation:
        rules.extend(
            [
                "- observe_screen 是理解用户当下状态的重要上下文工具。如果用户输入很短、模糊、寒暄、状态化，或希望获得建议、陪伴、下一步行动，但当前文字不足以判断当下处境，优先调用 observe_screen 获取当前屏幕，再回复。",
                "- 如果本轮已经包含 screen_context、screen_contexts 或图片，不要重复截图；直接基于已有画面判断。",
            ]
        )
    else:
        rules.append("- 当前没有可用的自主屏幕观察工具；不要请求截图，也不要臆造当前屏幕内容。")
    rules.extend(
        [
            "- 如果问题依赖最新、外部、公开或不确定的信息，主动使用可用的网页搜索工具；搜索摘要不足以回答时，再读取具体网页。",
            "- 如果问题主要依赖当前屏幕，先获取屏幕上下文；如果屏幕后仍需要外部事实，再搜索网页。",
            "- 如果信息已经足够，停止工具调用并自然回复。不要为了显得主动而循环调用工具。",
        ]
    )
    return "主动获取上下文策略：\n" + "\n".join(rules)


def build_proactive_rules(*, include_tool_rules: bool = False) -> str:
    rules = [
        "- 这是低打扰主动搭话，不是用户主动提问；如果没有明确问题，只说 1-2 段即可。",
        "- 如果事件附加了 screen_context.image_attached 或 screen_contexts，先理解屏幕画面本身，再围绕看见的内容自然评论、提问或轻提醒。",
        "- 如果事件附加了多张 screen_contexts，把它们当作一段时间内的画面变化来概括趋势，不要逐张机械描述。",
        "- seconds_since_pet_interaction 只表示用户一段时间没有和桌宠交互；不要据此推断用户离开、电脑没操作、屏幕没变化或没有活动。",
        "- 不要编造看不清的文字、文件名、错误码或用户意图；不确定时就轻轻询问或普通问候。",
        "- 避免机械套用休息、喝水、深呼吸等通用关怀；优先回应事件里真实可见或已知的具体内容。",
        "- 只能给建议或询问，不要声明自己已经执行任何工具、点击、打开网页或改变外部状态。",
        "- tone 和 portrait 要根据内容选择；主动搭话时不要固定使用“提醒”语气。",
    ]
    if include_tool_rules:
        rules.extend(
            [
                "- 可以使用只读或低风险工具补充上下文，例如读取当前时间、搜索已确认记忆、读取受控浏览器当前内容或状态。",
                "- 如果事件已经附加 screen_context.image_attached 或 screen_contexts，不要再请求 observe_screen。",
                "- 只有发现明确、有价值的后续线索时才继续下一步；不要为了显得主动而循环调用工具。",
                "- 不要主动执行会改变外部状态的工具，除非工具需要确认且你只是发起确认请求。",
                "- 最终回复只说给用户听的自然搭话、提问或轻提醒，不要提及内部事件、工具循环或工具协议。",
            ]
        )
    return "\n".join(rules)


def _build_segment_protocol(
    tones: list[str],
    portraits: list[str],
    *,
    format_text: str,
    segment_rules: str,
    include_translation_rules: bool,
) -> str:
    parts = [
        JSON_ONLY_INSTRUCTION,
        "JSON 格式如下：",
        format_text,
    ]
    if segment_rules:
        parts.extend(["", "分段规则：", segment_rules])
    parts.extend(
        [
            "",
            "要求：",
            f"- tone 只能从这些类别中选择：{'、'.join(tones)}。",
            f"- portrait 只能从这些类别中选择：{'、'.join(portraits)}。",
            "- ja 中只写夜乃桜要说出口的日文原文，必须是日语，适合直接交给日语 TTS 朗读。",
            "- ja 中不要有任何非日语内容，如果出现例如中文引用，把引用的中文内容翻译成日文放在 ja 字段里。",
            "- ja 中不要有英文单词，如果日文中夹杂着英文名词之类的，请使用片假名拼写替换原英文单词。",
            "- zh 中只写 ja 对应的自然中文译文，必须是中文，不要添加解释、括号动作、语气标签或额外内容。",
            "- 无论用户使用什么语言，ja 和 zh 都必须同时输出；不要只输出其中一种语言。",
            "- ja 和 zh 必须一一对应；不要为了翻译改变 ja 的角色语气或内容。",
        ]
    )
    if not include_translation_rules:
        parts = [
            part
            for part in parts
            if not part.startswith("- ja 中不要有任何非日语内容")
            and not part.startswith("- ja 中不要有英文单词")
            and not part.startswith("- 无论用户使用什么语言")
            and not part.startswith("- ja 和 zh 必须一一对应")
        ]
    return "\n".join(parts)


def _labels_or_default(labels: list[str] | None, default: list[str]) -> list[str]:
    normalized = [label.strip() for label in labels or [] if label.strip()]
    return normalized or [*default]
