import re

from loguru import logger

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./:%-]+|[\u4e00-\u9fff]|\s+|.", re.UNICODE)
_HIGH_SIGNAL_PATTERN = re.compile(
    r"CPU|内存|memory|磁盘|disk|timeout|超时|error|错误|异常|告警|报警|"
    r"service unavailable|unavailable|HTTP|status|状态码|错误码|日志|log|"
    r"服务|service|pod|container|k8s|kubernetes|主机|host|IP|[45]\d{2}|\d+%",
    re.IGNORECASE,
)
_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？!?；;\n])")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0

    total = 0
    for token in _TOKEN_PATTERN.findall(text):
        if token.isspace():
            continue
        if re.fullmatch(r"[A-Za-z0-9_./:%-]+", token):
            total += len(token)
        elif re.fullmatch(r"[\u4e00-\u9fff]", token):
            total += 1
        else:
            total += 1
    return total


def truncate_to_token_budget(text: str, max_tokens: int, keep: str = "tail") -> str:
    if not text or max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    source = reversed(text) if keep == "tail" else iter(text)
    selected = []
    for char in source:
        candidate = "".join(reversed(selected + [char])) if keep == "tail" else "".join(selected + [char])
        if estimate_tokens(candidate) > max_tokens:
            break
        selected.append(char)

    if keep == "tail":
        return "".join(reversed(selected)).strip()
    return "".join(selected).strip()


def compress_query_for_embedding(text: str, max_tokens: int) -> str:
    if not text or max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    segments = _split_segments(text)
    selected_indexes = _select_high_signal_segments(segments, max_tokens)

    if selected_indexes:
        compressed = "\n".join(segments[index] for index in sorted(selected_indexes)).strip()
        if estimate_tokens(compressed) <= max_tokens:
            logger.warning(
                f"Embedding 输入已智能压缩: original_tokens={estimate_tokens(text)}, "
                f"compressed_tokens={estimate_tokens(compressed)}, max_tokens={max_tokens}"
            )
            return compressed
        return truncate_to_token_budget(compressed, max_tokens)

    truncated = truncate_to_token_budget(text, max_tokens)
    logger.warning(
        f"Embedding 输入已尾部截断: original_tokens={estimate_tokens(text)}, "
        f"compressed_tokens={estimate_tokens(truncated)}, max_tokens={max_tokens}"
    )
    return truncated


def _split_segments(text: str) -> list[str]:
    raw_segments = []
    for line in text.splitlines():
        raw_segments.extend(_BOUNDARY_PATTERN.split(line))
    return [segment.strip() for segment in raw_segments if segment.strip()]


def _select_high_signal_segments(segments: list[str], max_tokens: int) -> set[int]:
    scored = []
    for index, segment in enumerate(segments):
        score = _score_segment(segment, index, len(segments))
        if score > 0:
            scored.append((score, index))

    selected = set()
    current_tokens = 0
    tail_budget = max(1, max_tokens // 4)
    for index in range(len(segments) - 1, -1, -1):
        segment_tokens = estimate_tokens(segments[index])
        if current_tokens + segment_tokens <= tail_budget:
            selected.add(index)
            current_tokens += segment_tokens
        elif not selected:
            selected.add(index)
            break
        else:
            break

    for _, index in sorted(scored, reverse=True):
        candidate_indexes = selected | {index}
        candidate = "\n".join(segments[item] for item in sorted(candidate_indexes))
        if estimate_tokens(candidate) <= max_tokens:
            selected.add(index)

    return selected


def _score_segment(segment: str, index: int, total_segments: int) -> int:
    score = 0
    matches = _HIGH_SIGNAL_PATTERN.findall(segment)
    score += len(matches) * 4
    if re.search(r"\b(?:[A-Za-z][A-Za-z0-9_-]*[-_])?[A-Za-z0-9_-]+(?:-api|-service|svc)\b", segment):
        score += 4
    if re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", segment):
        score += 4
    if re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", segment):
        score += 2
    if re.search(r"\b[A-Z]\d{3,}\b", segment):
        score += 4
    if total_segments and index >= total_segments * 0.75:
        score += 1
    return score
