from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction


def user_group_name(user_id):
    return f"user.{user_id}"


def publish_user_event(user_id, event, **data):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        user_group_name(user_id),
        {"type": "realtime.event", "event": event, "data": data},
    )


def publish_user_events_on_commit(user_ids, event, **data):
    for user_id in set(filter(None, user_ids)):
        transaction.on_commit(
            lambda user_id=user_id: publish_user_event(user_id, event, **data)
        )
