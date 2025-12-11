"""Helper functions for gliner

From https://github.com/urchade/GLiNER/issues/95
"""

import logging

logger = logging.getLogger(__name__)


def split_text_into_chunks(text: str, chunk_size: int) -> list[str]:
    words = text.split()
    return [
        " ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)
    ]


def calculate_offsets(chunks: list[str]) -> list[int]:
    offset = 0
    offsets = []
    for chunk in chunks:
        offsets.append(offset)
        offset += len(chunk) + 1  # +1 for the space that was removed during split
    return offsets


def adjust_indices(entities: list[dict], offset: int) -> list[dict]:
    for entity in entities:
        entity["start"] += offset
        entity["end"] += offset
    return entities


def predict_long_text(
    model, text: str, labels: list[str], chunk_size: int = 384
) -> list[dict]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    chunks = split_text_into_chunks(text, chunk_size)
    offsets = calculate_offsets(chunks)

    all_entities = []
    chunk_entities_list = model.batch_predict_entities(chunks, labels, threshold=0.5)

    for chunk_entities, offset in zip(chunk_entities_list, offsets):
        adjusted_entities = adjust_indices(chunk_entities, offset)
        all_entities.extend(adjusted_entities)

    return all_entities
