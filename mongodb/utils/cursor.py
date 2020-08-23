from models import Model

from typing import Generic, TypeVar, Type

T = TypeVar("T", bound=Model)


class ExtendedCursor(Generic[T]):
    def __init__(self, cursor, count, parse_cls: Type[T] = None):
        self._cursor = cursor
        self._count = count
        self._parse_cls = parse_cls

    def __iter__(self):
        for dict_ in self._cursor:
            if self._parse_cls:
                yield self._parse_cls(**dict_, from_db=True)
            else:
                yield dict_

    def __len__(self):
        return self._count

    def limit(self, limit):
        if limit:
            self._cursor = self._cursor.limit(limit)
        return self

    @property
    def empty(self):
        return len(self) == 0
