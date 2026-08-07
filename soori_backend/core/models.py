import uuid

from django.db import models


class UUIDModel(models.Model):
    """
    Every custom model in this project should inherit from this,
    instead of repeating `id = models.UUIDField(primary_key=True,
    default=uuid.uuid4, editable=False)` by hand on each one.

    Why this matters (the actual problem it solves): a plain
    auto-incrementing integer ID (Django's default, and what
    DEFAULT_AUTO_FIELD in settings.py falls back to for any model that
    doesn't specify otherwise) is only unique WITHIN one database.
    Ticket #47 in this database and Ticket #47 in a second database
    are two completely different rows that happen to share a number --
    merge or migrate those two databases together later (a second
    region, a larger DB, an acquisition merging two deployments) and
    you get real collisions: rows silently overwriting each other, or
    foreign keys pointing at the wrong record entirely.

    A UUID (a random 128-bit value) doesn't have this problem. The
    odds of two independently-generated UUIDs ever colliding are low
    enough to treat as impossible in practice -- so IDs generated in
    two completely separate databases, with no coordination between
    them, can be merged back together later with no renumbering and no
    conflict resolution needed. That's the actual guarantee "global
    standard" IDs are asking for.

    Inheriting from this class is what makes that guarantee automatic
    and structural for any NEW model, instead of relying on someone
    remembering to type the same field definition correctly every
    time. As a second line of defense -- in case a future model is
    written without inheriting from this -- see the automated check
    in core/checks.py, which flags any model in this project whose
    primary key isn't a UUID the moment you run `manage.py check`
    (which also runs automatically before `runserver`/`migrate`).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
