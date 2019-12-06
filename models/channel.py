from bson import ObjectId

from JellyBot.systemconfig import ChannelConfig
from models.field import (
    PlatformField, TextField, ModelField, IntegerField, BooleanField, ObjectIDField, DictionaryField, ArrayField
)


from ._base import Model, ModelDefaultValueExt


class ChannelConfigModel(Model):
    # TODO: Channel Config: Turn on/off features (Enable*) by votes if no mod/admin (% of 5 days active member)
    # TODO: Channel Config: Vote = 0 means no promo

    WITH_OID = False

    VotePromoMod = IntegerField("v-m", default=ChannelConfig.VotesToPromoteMod)
    VotePromoAdmin = IntegerField("v-a", default=ChannelConfig.VotesToPromoteAdmin)
    EnableAutoReply = BooleanField("e-ar", default=True)
    EnableTimer = BooleanField("e-tmr", default=True)
    EnableCalculator = BooleanField("e-calc", default=True)
    EnableBotCommand = BooleanField("e-bot", default=True)
    EnableCreateProfile = BooleanField("e-crp", default=True)
    InfoPrivate = BooleanField("prv", default=False)
    DefaultProfileOid = ObjectIDField("d-prof", allow_none=True)
    DefaultName = TextField("d-name", allow_none=True)


class ChannelModel(Model):
    Platform = PlatformField("p", default=ModelDefaultValueExt.Required)
    Token = TextField("t", default=ModelDefaultValueExt.Required, must_have_content=True)
    Name = DictionaryField("n", allow_none=False, default={})
    Config = ModelField("c", ChannelConfigModel)
    BotAccessible = BooleanField("acc", default=True)

    def get_channel_name(self, root_oid: ObjectId):
        oid_str = str(root_oid)

        if oid_str in self.name:
            return self.name[oid_str]
        else:
            return self.config.default_name or ""


class ChannelCollectionModel(Model):
    DefaultName = TextField("dn", default=ModelDefaultValueExt.Required, must_have_content=True)
    Name = DictionaryField("n", allow_none=False, default={})
    Platform = PlatformField("p", default=ModelDefaultValueExt.Required)
    Token = TextField("t", default=ModelDefaultValueExt.Required, must_have_content=True)
    BotAccessible = BooleanField("acc", default=True)
    ChildChannelOids = ArrayField("ch", elem_type=ObjectId)
