from datetime import datetime, timedelta


def group_slots_by_block(slots):
    blocks = dict()
    for slot in slots:
        if slot["block"] not in blocks:
            blocks[slot["block"]] = list()
        blocks[slot["block"]].append(slot)

    for block in blocks.keys():
        blocks[block] = sorted(blocks[block], key=lambda b: b["ends_at"])

    return blocks


def query_range(days_range):
    query_start = (datetime.utcnow() + timedelta(days=days_range[0])).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    query_end = (datetime.utcnow() + timedelta(days=days_range[1])).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return query_start, query_end
