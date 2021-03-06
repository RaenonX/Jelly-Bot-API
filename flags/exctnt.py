"""Module for extra content type flags."""
from django.utils.translation import gettext_lazy as _

from extutils.flags import FlagSingleEnum


class ExtraContentType(FlagSingleEnum):
    """Defined extra content types."""

    @classmethod
    def default(cls):
        return ExtraContentType.PURE_TEXT

    PURE_TEXT = 0, _("Pure Text")
    EXTRA_MESSAGE = 1, _("Extra Message")

    AUTO_REPLY_SEARCH = 100, _("Auto Reply Search Result")
