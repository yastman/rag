"""RU/UK query normalizer -- strips semantic noise for better cache hit rates."""

import re


# --- Greetings (anchored to start, optional comma/punctuation after) ---
_GREETINGS = re.compile(
    r"^\s*(?:"
    # RU greetings
    r"добрый\s+(?:день|вечер|утро)"
    r"|доброе\s+утро"
    r"|здравствуйте"
    r"|здрасте"
    r"|приветствую"
    r"|привет"
    r"|хей"
    r"|хай"
    r"|алло"
    # UK greetings
    r"|добрий\s+(?:день|вечір)"
    r"|доброго\s+ранку"
    r"|привіт"
    r"|вітаю"
    r")[!,.\s]*",
    re.IGNORECASE | re.UNICODE,
)

# --- Polite requests (can appear after greeting or standalone) ---
_POLITE_REQUESTS = re.compile(
    r"(?:"
    # RU polite requests
    r"подскажите\s+пожалуйста"
    r"|расскажите\s+пожалуйста"
    r"|скажите\s+пожалуйста"
    r"|объясните\s+пожалуйста"
    r"|не\s+могли\s+бы\s+вы"
    r"|будьте\s+добры"
    r"|можете\s+(?:рассказать|подсказать|объяснить)"
    r"|можешь\s+(?:рассказать|подсказать|объяснить)"
    r"|подскажите"
    r"|расскажите"
    # UK polite requests
    r"|підкажіть\s+будь\s+ласка"
    r"|розкажіть\s+будь\s+ласка"
    r"|скажіть\s+будь\s+ласка"
    r"|поясніть\s+будь\s+ласка"
    r"|чи\s+не\s+могли\s+б\s+ви"
    r"|чи\s+можете"
    r"|підкажіть"
    r"|розкажіть"
    r")[,.\s]*",
    re.IGNORECASE | re.UNICODE,
)

# --- Polite tails (anchored to end) ---
_POLITE_TAILS = re.compile(
    r"[,.\s]*(?:"
    # RU tails
    r"заранее\s+(?:спасибо|благодарю)"
    r"|буду\s+(?:благодарен|благодарна|признателен|признательна)"
    r"|спасибо"
    r"|благодарю"
    # UK tails
    r"|заздалегідь\s+дякую"
    r"|дякую\s+за\s+відповідь"
    r"|буду\s+(?:вдячний|вдячна)"
    r"|дякую"
    r")\s*[!.]*\s*$",
    re.IGNORECASE | re.UNICODE,
)

# --- Filler words (standalone, word boundaries) ---
_FILLERS = re.compile(
    r"\b(?:"
    # RU fillers
    r"пожалуйста"
    r"|так\s+сказать"
    r"|в\s+общем"
    r"|как\s+бы"
    r"|короче"
    r"|значит"
    r"|типа"
    r"|вот"
    r"|ну"
    # UK fillers
    r"|будь\s+ласка"
    r"|як\s+би"
    r"|загалом"
    r"|от"
    r")\b[,.\s]*",
    re.IGNORECASE | re.UNICODE,
)

# Collapse multiple whitespace
_MULTI_SPACE = re.compile(r"\s{2,}")


def normalize_ru_uk(query: str) -> str:
    """Strip greetings, polite phrases, filler words from RU/UK queries.

    Processing order: greetings -> polite requests -> polite tails -> fillers.
    If the result is empty or < 3 chars, returns the original query unchanged.
    """
    original = query
    text = query

    # 1. Strip greetings (anchored to start)
    text = _GREETINGS.sub("", text)

    # 2. Strip polite requests
    text = _POLITE_REQUESTS.sub("", text)

    # 3. Strip polite tails (anchored to end)
    text = _POLITE_TAILS.sub("", text)

    # 4. Strip filler words
    text = _FILLERS.sub(" ", text)

    # Normalize whitespace
    text = _MULTI_SPACE.sub(" ", text).strip()

    # Safety: if result is too short, return original
    if len(text) < 3:
        return original

    return text
