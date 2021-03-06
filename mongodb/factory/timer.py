"""Data manager for the timers."""
from datetime import datetime, timedelta
from typing import Optional, List

import pymongo
from bson import ObjectId

from models import TimerModel, TimerListResult, OID_KEY
from mongodb.factory.results import WriteOutcome
from extutils.checker import arg_type_ensure
from extutils.locales import UTC
from extutils.dt import is_tz_naive, now_utc_aware, make_tz_aware
from JellyBot.systemconfig import Bot

from ._base import BaseCollection

__all__ = ("TimerManager",)

DB_NAME = "timer"


class _TimerManager(BaseCollection):
    database_name = DB_NAME
    collection_name = "timer"
    model_class = TimerModel

    def build_indexes(self):
        self.create_index(TimerModel.Keyword.key)
        self.create_index(TimerModel.DeletionTime.key, expireAfterSeconds=0)

    @arg_type_ensure
    def add_new_timer(
            self, ch_oid: ObjectId, keyword: str, title: str, target_time: datetime, *,
            countup: bool = False, period_sec: int = 0) -> WriteOutcome:
        """`target_time` is recommended to be tz-aware. Tzinfo will be forced to be UTC if tz-naive."""
        # Force target time to be tz-aware in UTC
        if is_tz_naive(target_time):
            target_time = make_tz_aware(target_time, UTC.to_tzinfo())

        mdl = TimerModel(
            ChannelOid=ch_oid, Keyword=keyword, Title=title, TargetTime=target_time,
            Countup=countup, PeriodSeconds=period_sec)

        if not countup:
            mdl.deletion_time = target_time + timedelta(days=Bot.Timer.AutoDeletionDays)
            mdl.deletion_time = make_tz_aware(mdl.deletion_time, target_time.tzinfo)

        outcome, _ = self.insert_one_model(mdl)

        return outcome

    @arg_type_ensure
    def del_timer(self, timer_oid: ObjectId) -> bool:
        """
        Delete the timer by its OID.

        :param timer_oid: OID of the timer to be deleted
        :return: if the timer was successfully deleted
        """
        return self.delete_one({OID_KEY: timer_oid}).deleted_count > 0

    @arg_type_ensure
    def list_all_timer(self, channel_oid: ObjectId) -> TimerListResult:
        """
        List all the timers in the channel ``channel_oid``.

        All timers in the returned result will be sorted by its target time (ASC).

        :param channel_oid: channel of the timers
        :return: a `TimerListResult` containing the timers that match the conditions
        """
        return TimerListResult(
            self.find_cursor_with_count(
                {TimerModel.ChannelOid.key: channel_oid},
                sort=[(TimerModel.TargetTime.key, pymongo.ASCENDING)]
            )
        )

    @arg_type_ensure
    def get_timers(self, channel_oid: ObjectId, keyword: str) -> TimerListResult:
        """
        Get the timers in the channel ``channel_oid`` which keyword ``keyword``.

        ``keyword`` needs to be an exact match, **NOT** partial match.

        All timers in the returned result will be sorted by its target time (ASC).

        :param channel_oid: channel of the timers
        :param keyword: keyword of the timers
        :return: a `TimerListResult` containing the timers that match the conditions
        """
        return TimerListResult(
            self.find_cursor_with_count(
                {TimerModel.Keyword.key: keyword, TimerModel.ChannelOid.key: channel_oid},
                sort=[(TimerModel.TargetTime.key, pymongo.ASCENDING)]
            )
        )

    @arg_type_ensure
    def get_notify(self, channel_oid: ObjectId, within_secs: Optional[int] = None) -> List[TimerModel]:
        """
        Get a list of unnotified timers which will timeup in ``within_secs`` seconds in ``channel_oid``.

        Returned timers will be sorted by its target time (ASC).

        :param channel_oid: channel of the timers
        :param within_secs: timers that will timeup within this amount of seconds will be returned
        :return: a list of timers that is not yet notified and will timeup in `within_secs` seconds
        """
        now = now_utc_aware()

        filter_ = {
            TimerModel.ChannelOid.key: channel_oid,
            TimerModel.TargetTime.key: {
                "$lt": now + timedelta(seconds=within_secs if within_secs else Bot.Timer.MaxNotifyRangeSeconds),
                "$gt": now
            },
            TimerModel.Notified.key: False
        }

        ret = list(self.find_cursor_with_count(filter_, sort=[(TimerModel.TargetTime.key, pymongo.ASCENDING)]))

        self.update_many_async(filter_, {"$set": {TimerModel.Notified.key: True}})

        return ret

    @arg_type_ensure
    def get_time_up(self, channel_oid: ObjectId) -> List[TimerModel]:
        """
        Get a list of unnotified timers which timed up in ``channel_oid``.

        All timers in the returned result will be sorted by its target time (ASC).

        :param channel_oid: channel of the timers
        :return: a list of timers that is not yet notified and already timed up
        """
        now = now_utc_aware()

        filter_ = {
            TimerModel.ChannelOid.key: channel_oid,
            TimerModel.TargetTime.key: {"$lt": now},
            TimerModel.NotifiedExpired.key: False
        }

        ret = list(self.find_cursor_with_count(filter_, sort=[(TimerModel.TargetTime.key, pymongo.ASCENDING)]))

        self.update_many_async(filter_, {"$set": {TimerModel.NotifiedExpired.key: True}})

        return ret

    @staticmethod
    def get_notify_within_secs(message_frequency: float):
        """
        Get a time range calculated by ``message_frequency`` which can be used to get the timers for notification.

        Calculate formula: **message frequency x 20 + 600**

        If the calculated result is greater than ``Bot.Timer.MaxNotifyRangeSeconds``,
        then ``Bot.Timer.MaxNotifyRangeSeconds`` will be returned instead.

        :param message_frequency: message frequency in seconds per message
        :return: time range to be used to get the timers for notification
        """
        return min(message_frequency * 20 + 600, Bot.Timer.MaxNotifyRangeSeconds)


TimerManager = _TimerManager()
