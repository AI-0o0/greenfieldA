from typing import List, Callable
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage


def _split_system(messages: List[BaseMessage]):
    if messages and isinstance(messages[0], SystemMessage):
        return messages[0], messages[1:]
    return None, messages


# ============================================================
# 1. Sliding Window — keep last N messages, drop everything older
# ============================================================
def sliding_window(messages: List[BaseMessage], keep_recent: int = 10) -> List[BaseMessage]:
    system, history = _split_system(messages)
    pruned = history[-keep_recent:] if len(history) > keep_recent else history
    return ([system] if system else []) + pruned


# ============================================================
# 2. Observation Masking — blank out old tool outputs, keep dialogue
# ============================================================
def observation_masking(messages: List[BaseMessage], keep_recent_observations: int = 3) -> List[BaseMessage]:
    system, history = _split_system(messages)
    obs_idx = [
        i for i, m in enumerate(history)
        if isinstance(m, HumanMessage) and str(m.content).startswith("[Observation]:")
    ]
    to_mask = obs_idx[:-keep_recent_observations] if len(obs_idx) > keep_recent_observations else []
    masked = list(history)
    for i in to_mask:
        masked[i] = HumanMessage(content="[Observation omitted — see earlier reasoning above]")
    return ([system] if system else []) + masked


# ============================================================
# 3. Recursive Summarization — compact old turns into one summary
# ============================================================
def recursive_summarization(messages: List[BaseMessage], llm, keep_recent: int = 6) -> List[BaseMessage]:
    system, history = _split_system(messages)
    if len(history) <= keep_recent:
        return messages

    old, recent = history[:-keep_recent], history[-keep_recent:]
    old_text = "\n".join(f"{m.type}: {m.content}" for m in old)
    summary = llm.invoke(
        "Summarize the conversation below. Preserve decisions made, unresolved "
        "issues, and key findings. Discard redundant tool output and superseded "
        f"reasoning.\n\n{old_text}"
    ).content

    result = []
    if system:
        result.append(system)
    result.append(SystemMessage(content=f"Earlier context (summarized): {summary}"))
    result.extend(recent)
    return result


# ============================================================
# 4. Zone-Based Pruning — newest kept, mid masked, older summarized, oldest dropped
# ============================================================
def zone_based_pruning(
    messages: List[BaseMessage],
    llm,
    zone_sizes: tuple = (4, 6, 10),  # (newest, masked, summarized) — beyond this: dropped
) -> List[BaseMessage]:
    system, history = _split_system(messages)
    n = len(history)
    z1, z2, z3 = zone_sizes

    newest = history[-z1:] if n > 0 else []
    masked_zone = history[-(z1 + z2):-z1] if n > z1 else []
    summarized_zone = history[-(z1 + z2 + z3):-(z1 + z2)] if n > z1 + z2 else []
    # anything older than z1+z2+z3 is dropped entirely — that's the "oldest: delete" zone

    masked = [
        HumanMessage(content="[Observation omitted]")
        if isinstance(m, HumanMessage) and str(m.content).startswith("[Observation]:") else m
        for m in masked_zone
    ]

    result = []
    if system:
        result.append(system)
    if summarized_zone:
        old_text = "\n".join(f"{m.type}: {m.content}" for m in summarized_zone)
        summary = llm.invoke(f"Summarize concisely, preserving key decisions:\n\n{old_text}").content
        result.append(SystemMessage(content=f"Zone summary (older history): {summary}"))
    result.extend(masked)
    result.extend(newest)
    return result