from typing import Tuple, Optional, List

import math
import pymongo
from bson import ObjectId
from datetime import datetime

from JellyBotAPI.SystemConfig import Database, DataQuery
from extutils import is_empty_string
from extutils.gmail import MailSender
from extutils.checker import DecoParamCaster
from extutils.color import ColorFactory
from flags import PermissionCategory, AutoReplyContentType
from models import AutoReplyModuleModel, AutoReplyModuleTagModel, AutoReplyTagPopularityDataModel, OID_KEY
from mongodb.factory.results import (
    InsertOutcome, GetOutcome,
    AutoReplyModuleAddResult, AutoReplyModuleTagGetResult
)
from mongodb.utils import CheckableCursor
from mongodb.factory import ProfileManager, AutoReplyContentManager

from ._base import BaseCollection

DB_NAME = "ar"


class AutoReplyModuleManager(BaseCollection):
    # TODO: Auto Reply - Cache & Preload
    database_name = DB_NAME
    collection_name = "conn"
    model_class = AutoReplyModuleModel

    def __init__(self):
        super().__init__(AutoReplyModuleModel.Id.key)
        self.create_index(
            [(AutoReplyModuleModel.KeywordOid.key, 1), (AutoReplyModuleModel.ResponsesOids.key, 1)],
            name="Auto Reply Module Identity", unique=True)

    def add_conn(
            self,
            kw_oid: ObjectId, rep_oids: Tuple[ObjectId], creator_oid: ObjectId, channel_oid: ObjectId,
            pinned: bool, private: bool, tag_ids: List[ObjectId], cooldown_sec: int) \
            -> AutoReplyModuleAddResult:
        perms = ProfileManager.get_permissions(ProfileManager.get_user_profiles(channel_oid, creator_oid))
        if pinned and PermissionCategory.AR_ACCESS_PINNED_MODULE not in perms:
            return AutoReplyModuleAddResult(InsertOutcome.X_INSUFFICIENT_PERMISSION, None, None)
        else:
            model, outcome, ex, insert_result = \
                self.insert_one_data(
                    AutoReplyModuleModel,
                    KeywordOid=kw_oid, ResponsesOids=rep_oids, CreatorOid=creator_oid, Pinned=pinned,
                    Private=private, CooldownSec=cooldown_sec, TagIds=tag_ids, ChannelIds=[channel_oid]
                )

            if outcome.is_success:
                self.set_cache(AutoReplyModuleModel.Id.key, model.id, model)

            return AutoReplyModuleAddResult(outcome, model, ex)

    def add_conn_by_model(self, model: AutoReplyModuleModel) -> AutoReplyModuleAddResult:
        model.clear_oid()
        outcome, ex = self.insert_one_model(model)

        if outcome.is_success:
            self.set_cache(AutoReplyModuleModel.Id.key, model.id, model)

        return AutoReplyModuleAddResult(outcome, model, ex)

    def append_channel(self, kw_oid: ObjectId, rep_oids: Tuple[ObjectId], channel_oid: ObjectId) -> InsertOutcome:
        update_result = self.update_one(
            {AutoReplyModuleModel.KeywordOid.key: kw_oid, AutoReplyModuleModel.ResponsesOids.key: rep_oids},
            {"$addToSet": {AutoReplyModuleModel.ChannelIds.key: channel_oid}})

        if update_result.matched_count > 0:
            if update_result.modified_count > 0:
                outcome = InsertOutcome.O_INSERTED
            else:
                outcome = InsertOutcome.O_DATA_EXISTS
        else:
            outcome = InsertOutcome.X_NOT_FOUND

        if outcome.is_success:
            self.remove_cache(AutoReplyModuleModel.Id.key, update_result.upserted_id)

        return outcome

    @DecoParamCaster({1: ObjectId, 2: bool})
    def get_conn(self, keyword_oid: ObjectId, case_insensitive: bool = True) -> Optional[AutoReplyModuleModel]:
        return self.get_cache(
            AutoReplyModuleModel.Id.key,
            keyword_oid, parse_cls=AutoReplyModuleModel, case_insensitive=case_insensitive)


class AutoReplyModuleTagManager(BaseCollection):
    database_name = DB_NAME
    collection_name = "tag"
    model_class = AutoReplyModuleTagModel

    def __init__(self):
        super().__init__(AutoReplyModuleTagModel.Name.key)
        self.create_index(AutoReplyModuleTagModel.Name.key, name="Auto Reply Tag Identity", unique=True)

    def get_insert(self, name, color=ColorFactory.BLACK) -> AutoReplyModuleTagGetResult:
        ex = None
        tag_data = self.get_cache(
            AutoReplyModuleTagModel.Name.key, name, parse_cls=AutoReplyModuleTagModel, case_insensitive=True)

        if tag_data:
            outcome = GetOutcome.O_CACHE_DB
        else:
            model, outcome, ex, insert_result = \
                self.insert_one_data(AutoReplyModuleTagModel, Name=name, Color=color)

            if outcome.is_success:
                tag_data = self.set_cache(
                    AutoReplyModuleTagModel.Name.key, name, tag_data, parse_cls=AutoReplyModuleTagModel)
                outcome = GetOutcome.O_ADDED
            else:
                outcome = GetOutcome.X_NOT_FOUND_ATTEMPTED_INSERT

        return AutoReplyModuleTagGetResult(outcome, tag_data, ex)

    def search_tags(self, tag_keyword: str) -> CheckableCursor:
        """
        Accepts a keyword to search. Case-insensitive.

        :param tag_keyword: Can be regex.
        """
        return CheckableCursor(
            self.find({"name": {"$regex": tag_keyword, "$options": "i"}}).sort([("_id", pymongo.DESCENDING)]),
            parse_cls=AutoReplyModuleTagModel)

    def get_tag_data(self, tag_oid: ObjectId) -> Optional[AutoReplyModuleTagModel]:
        return self.get_cache_condition(
            AutoReplyModuleTagModel.Name.key, lambda item: item.id == tag_oid,
            ({OID_KEY: tag_oid},), parse_cls=AutoReplyModuleTagModel)


class AutoReplyManager:
    def __init__(self):
        self._mod = AutoReplyModuleManager()
        self._tag = AutoReplyModuleTagManager()

    def _get_tags_pop_score_(self, filter_word: str = None, count: int = DataQuery.TagPopularitySearchCount) \
            -> CheckableCursor:
        # Time Past Weighting: https://www.desmos.com/calculator/db92kdecxa
        # Appearance Weighting: https://www.desmos.com/calculator/a2uv5pqqku

        pipeline = []

        if not is_empty_string(filter_word):
            pipeline.append({"$match": {
                "$or": [{OID_KEY: tag_data.id for tag_data in self._tag.search_tags(filter_word)}]}})

        pipeline.append({"$unwind": "$" + AutoReplyModuleModel.TagIds.key})
        pipeline.append({"$group": {
            "_id": "$" + AutoReplyModuleModel.TagIds.key,
            AutoReplyTagPopularityDataModel.WeightedAvgTimeDiff.key: {
                "$avg": {
                    "$divide": [
                        Database.PopularityConfig.TimeCoeffA,
                        {"$add": [
                            1,
                            {"$pow": [
                                math.e,
                                {"$multiply": [
                                    Database.PopularityConfig.TimeCoeffB,
                                    {"$subtract": [
                                        {"$divide": [
                                            {"$subtract": [
                                                {"$toDate": ObjectId.from_datetime(datetime.utcnow())},
                                                {"$toDate": "$" + AutoReplyTagPopularityDataModel.Id.key}
                                            ]},
                                            3600000
                                        ]},
                                        Database.PopularityConfig.TimeDiffIntersectHr
                                    ]}
                                ]}
                            ]}
                        ]}
                    ]
                }
            },
            AutoReplyTagPopularityDataModel.Appearances.key: {"$sum": 1}
        }})
        pipeline.append({"$addFields": {
            AutoReplyTagPopularityDataModel.WeightedAppearances.key: {
                "$multiply": [
                    Database.PopularityConfig.AppearanceCoeffA,
                    {"$pow": [
                        "$" + AutoReplyTagPopularityDataModel.Appearances.key,
                        Database.PopularityConfig.AppearanceFunctionCoeff
                    ]}
                ]
            }
        }})
        pipeline.append({"$addFields": {
            AutoReplyTagPopularityDataModel.Score.key: {
                "$subtract": [
                    {"$multiply": [
                        Database.PopularityConfig.AppearanceEquivalentWHr,
                        "$" + AutoReplyTagPopularityDataModel.WeightedAppearances.key
                    ]},
                    "$" + AutoReplyTagPopularityDataModel.WeightedAvgTimeDiff.key
                ]
            }
        }})
        pipeline.append({"$sort": {
            AutoReplyTagPopularityDataModel.Score.key: pymongo.DESCENDING
        }})
        pipeline.append({"$limit": count})

        return CheckableCursor(self._mod.aggregate(pipeline), parse_cls=AutoReplyTagPopularityDataModel)

    def add_conn_by_model(self, model: AutoReplyModuleModel) -> AutoReplyModuleAddResult:
        return self._mod.add_conn_by_model(model)

    def add_conn(
            self, kw_oid: ObjectId, rep_oids: Tuple[ObjectId], creator_oid: ObjectId, channel_oid: ObjectId,
            pinned: bool, private: bool, tag_ids: List[ObjectId], cooldown_sec: int) \
            -> AutoReplyModuleAddResult:
        return self._mod.add_conn(kw_oid, rep_oids, creator_oid, channel_oid, pinned, private, tag_ids, cooldown_sec)

    def get_response(
            self, keyword: str, type_: AutoReplyContentType, case_insensitive: bool = False) -> List[str]:
        """
        :return: Empty list (length of 0) if no corresponding response.
        """
        ctnt_rst = AutoReplyContentManager.get_content(keyword, type_, False, case_insensitive)
        mod = None
        resp_ctnt = []
        resp_id_miss = []

        if ctnt_rst.success:
            mod = self._mod.get_conn(ctnt_rst.model.id, case_insensitive)

        if mod:
            resp_ids = mod.response_oids

            for resp_id in resp_ids:
                ctnt = AutoReplyContentManager.get_content_by_id(resp_id)
                if ctnt:
                    resp_ctnt.append(ctnt)
                else:
                    resp_id_miss.append(resp_id)

        if not resp_id_miss or not mod:
            content = f"""Malformed data detected.
            <hr>
            <h4>Parameters</h4>\n
            Keyword: {keyword} / Type: {type_} / Case Insensitive: {case_insensitive}\n
            <h4>Variables</h4>\n
            Get content result (keyword): {ctnt_rst}\n
            Keyword connection model: {mod}\n
            Contents to response: {mod}\n
            Contents missing (id): {resp_id_miss}\n
            """
            MailSender.send_email_async(content, subject="Lossy data in auto reply database")

        return resp_ctnt

    def get_popularity_scores(self, search_keyword: str = None, count: int = DataQuery.TagPopularitySearchCount) \
            -> List[str]:
        """
        Get the :class:`list` of popular tag names sorted by the popularity score.
        """
        ret = []

        for score_model in self._get_tags_pop_score_(search_keyword, count):
            tag_data = self._tag.get_tag_data(score_model.id)
            if tag_data:
                ret.append(tag_data.name)

        return ret

    def tag_get_insert(self, name, color=ColorFactory.BLACK) -> AutoReplyModuleTagGetResult:
        return self._tag.get_insert(name, color)


_inst = AutoReplyManager()
