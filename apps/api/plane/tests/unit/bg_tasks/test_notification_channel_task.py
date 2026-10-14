# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from unittest.mock import patch

import pytest
from django.utils import timezone

from plane.bgtasks.notification_channel_task import deliver_channel_notification, dispatch_channel_notifications
from plane.db.models import Notification, NotificationDelivery, ProjectMember, UserNotificationChannel
from plane.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory
from plane.utils.notification_channels import ChannelError

MOD = "plane.bgtasks.notification_channel_task"
CONFIG = {
    "ENABLE_TELEGRAM_NOTIFICATIONS": "1",
    "TELEGRAM_BOT_TOKEN": "123:ABC",
    "TELEGRAM_BOT_USERNAME": "bot",
    "ENABLE_WHATSAPP_NOTIFICATIONS": "0",
    "WHATSAPP_PROVIDER_URL": "",
    "WHATSAPP_API_KEY": "",
    "WHATSAPP_INSTANCE_NAME": "plane",
    "NOTIFICATION_CHANNEL_EVENTS": "state_change,issue_completed,comment,mention,property_change",
}


@pytest.fixture
def setup(db):
    receiver = UserFactory()
    project = ProjectFactory()
    ProjectMemberFactory(project=project, workspace=project.workspace, member=receiver, is_active=True)
    notification = Notification.objects.create(
        workspace=project.workspace,
        project=project,
        receiver=receiver,
        entity_name="issue",
        title="t",
        sender="in_app:issue_activities:updated",
        data={
            "issue": {
                "id": "x",
                "name": "Tarefa",
                "identifier": "PRJ",
                "sequence_id": 1,
                "state_name": "Done",
                "state_group": "completed",
            },
            "issue_activity": {"field": "state", "new_value": "Done", "old_value": "Todo", "verb": "updated"},
        },
    )
    row = UserNotificationChannel.objects.create(
        user=receiver,
        channel="telegram",
        address="999",
        enabled=True,
        consented_at=timezone.now(),
        verified_at=timezone.now(),
    )
    delivery = NotificationDelivery.objects.create(notification=notification, channel="telegram")
    return notification, row, delivery


def run(delivery, config=None):
    with patch(f"{MOD}.get_channel_config", return_value=dict(config or CONFIG)):
        deliver_channel_notification.run(str(delivery.id))
    delivery.refresh_from_db()
    return delivery


@pytest.mark.unit
class TestDeliverChannelNotification:
    @patch(f"{MOD}.telegram_send", return_value="42")
    def test_sends(self, send, setup):
        d = run(setup[2])
        assert (d.status, d.attempts, d.external_id) == ("sent", 1, "42")
        send.assert_called_once()
        assert send.call_args.args[1] == "999"

    @pytest.mark.parametrize(
        "mutate,config,reason",
        [
            (lambda r: setattr(r, "consented_at", None), {}, "not_linked_or_no_consent"),
            (lambda r: setattr(r, "verified_at", None), {}, "not_linked_or_no_consent"),
            (lambda r: setattr(r, "enabled", False), {}, "not_linked_or_no_consent"),
            (lambda r: None, {"NOTIFICATION_CHANNEL_EVENTS": "comment"}, "event_disabled_by_admin"),
            (lambda r: setattr(r, "events", ["comment"]), {}, "event_disabled_by_user"),
            (lambda r: None, {"ENABLE_TELEGRAM_NOTIFICATIONS": "0"}, "channel_disabled"),
        ],
    )
    @patch(f"{MOD}.telegram_send", return_value="42")
    def test_skips(self, send, setup, mutate, config, reason):
        _, row, delivery = setup
        mutate(row)
        row.save()
        d = run(delivery, {**CONFIG, **config})
        assert (d.status, d.reason) == ("skipped", reason)
        send.assert_not_called()

    @patch(f"{MOD}.telegram_send", return_value="42")
    def test_skips_without_project_access(self, send, setup):
        notification, _, delivery = setup
        ProjectMember.objects.filter(member=notification.receiver).update(is_active=False)
        d = run(delivery)
        assert (d.status, d.reason) == ("skipped", "no_project_access")
        send.assert_not_called()

    @patch(f"{MOD}.telegram_send", side_effect=ChannelError("HTTP 401", transient=False))
    def test_permanent_error_fails(self, send, setup):
        d = run(setup[2])
        assert (d.status, d.attempts, d.reason) == ("failed", 1, "HTTP 401")

    @patch(f"{MOD}.telegram_send", return_value="42")
    def test_already_sent_is_not_resent(self, send, setup):
        delivery = setup[2]
        delivery.status = "sent"
        delivery.save()
        run(delivery)
        send.assert_not_called()


@pytest.mark.unit
@patch(f"{MOD}.get_channel_config", return_value=dict(CONFIG))
@patch(f"{MOD}.deliver_channel_notification")
def test_dispatch_is_idempotent(deliver, _config, setup):
    notification, _, delivery = setup
    delivery.delete()
    NotificationDelivery.all_objects.filter(notification=notification).delete()
    dispatch_channel_notifications([str(notification.id)])
    dispatch_channel_notifications([str(notification.id)])
    assert NotificationDelivery.objects.filter(notification=notification).count() == 1
    deliver.delay.assert_called_once()
