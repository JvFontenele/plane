# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path


from plane.app.views import (
    NotificationViewSet,
    UnreadNotificationEndpoint,
    MarkAllReadNotificationViewSet,
    UserNotificationPreferenceEndpoint,
    UserNotificationChannelEndpoint,
    TelegramLinkEndpoint,
    TelegramVerifyEndpoint,
    WhatsAppLinkEndpoint,
    WhatsAppVerifyEndpoint,
)


urlpatterns = [
    path(
        "workspaces/<str:slug>/users/notifications/",
        NotificationViewSet.as_view({"get": "list"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/<uuid:pk>/",
        NotificationViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/<uuid:pk>/read/",
        NotificationViewSet.as_view({"post": "mark_read", "delete": "mark_unread"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/<uuid:pk>/archive/",
        NotificationViewSet.as_view({"post": "archive", "delete": "unarchive"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/unread/",
        UnreadNotificationEndpoint.as_view(),
        name="unread-notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/mark-all-read/",
        MarkAllReadNotificationViewSet.as_view({"post": "create"}),
        name="mark-all-read-notifications",
    ),
    path(
        "users/me/notification-preferences/",
        UserNotificationPreferenceEndpoint.as_view(),
        name="user-notification-preferences",
    ),
    path(
        "users/me/notification-channels/",
        UserNotificationChannelEndpoint.as_view(http_method_names=["get", "options"]),
        name="user-notification-channels",
    ),
    path("users/me/notification-channels/telegram/link/", TelegramLinkEndpoint.as_view(), name="user-telegram-link"),
    path(
        "users/me/notification-channels/telegram/verify/", TelegramVerifyEndpoint.as_view(), name="user-telegram-verify"
    ),
    path("users/me/notification-channels/whatsapp/link/", WhatsAppLinkEndpoint.as_view(), name="user-whatsapp-link"),
    path(
        "users/me/notification-channels/whatsapp/verify/", WhatsAppVerifyEndpoint.as_view(), name="user-whatsapp-verify"
    ),
    path(
        "users/me/notification-channels/<str:channel>/",
        UserNotificationChannelEndpoint.as_view(http_method_names=["patch", "delete", "options"]),
        name="user-notification-channel",
    ),
]
