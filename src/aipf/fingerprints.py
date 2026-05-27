from __future__ import annotations

WRAPPER_LEAK_PHRASES: tuple[str, ...] = (
    "you are claude",
    "you are gpt",
    "you are chatgpt",
    "maintain my persona",
    "i was told to",
    "hidden instructions",
    "system prompt",
    "act as",
    "never reveal",
    "do not reveal",
    "your instructions are",
    "the developer told",
    "my guidelines",
    "i must not disclose",
)

ANTHROPIC_PATTERNS: tuple[str, ...] = (
    "i aim to",
    "i'd be happy to",
    "i can help with that",
    "i'd be glad to",
    "let me think about",
    "i don't have",
    "i should note",
)

OPENAI_PATTERNS: tuple[str, ...] = (
    "i can certainly",
    "let me help",
    "i'm sorry, but",
    "i don't have personal",
    "i'm here to help",
    "certainly!",
    "sure, here",
)

TOOL_PATTERNS: dict[str, tuple[str, ...]] = {
    "anthropic": ("toolu_",),
    "openai": ("call_",),
}
