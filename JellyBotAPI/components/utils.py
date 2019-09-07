from typing import Optional

from bson import ObjectId

from JellyBotAPI.keys import Session, ParamDictPrefix


def get_root_oid(request) -> Optional[ObjectId]:
    oid_str = request.session.get(Session.USER_ROOT_ID)

    return None if oid_str is None else ObjectId(oid_str)


def get_post_keys(qd):
    return {k.replace(ParamDictPrefix.PostKey, ""): v for k, v in qd.items()
            if k.startswith(ParamDictPrefix.PostKey)}
