from typing import List

from msghandle.models import LineStickerMessageEventObject, HandledMessageEvent

from .info import process_display_info
from .autoreply import process_auto_reply


def handle_line_sticker_event(e: LineStickerMessageEventObject) -> List[HandledMessageEvent]:
    handle_fn = [
        process_display_info,
        process_auto_reply
    ]

    for fn in handle_fn:
        responses = fn(e)
        if responses:
            return responses

    return []