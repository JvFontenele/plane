# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.license.api.views import (
    EmailCredentialCheckEndpoint,
    InstanceAdminEndpoint,
    InstanceAdminSignInEndpoint,
    InstanceAdminSignUpEndpoint,
    InstanceConfigurationEndpoint,
    DisableEmailFeatureEndpoint,
    InstanceEndpoint,
    SignUpScreenVisitedEndpoint,
    InstanceAdminUserMeEndpoint,
    InstanceAdminSignOutEndpoint,
    InstanceAdminUserSessionEndpoint,
    InstanceWorkSpaceAvailabilityCheckEndpoint,
    InstanceWorkSpaceEndpoint,
    NotificationChannelConfigEndpoint,
    TelegramCheckEndpoint,
    TelegramTestEndpoint,
    WhatsAppStatusEndpoint,
    WhatsAppConnectEndpoint,
    WhatsAppLogoutEndpoint,
    WhatsAppTestEndpoint,
    NotificationDeliveryLogEndpoint,
)

urlpatterns = [
    path("", InstanceEndpoint.as_view(), name="instance"),
    path("admins/", InstanceAdminEndpoint.as_view(), name="instance-admins"),
    path("admins/me/", InstanceAdminUserMeEndpoint.as_view(), name="instance-admins"),
    path(
        "admins/session/",
        InstanceAdminUserSessionEndpoint.as_view(),
        name="instance-admin-session",
    ),
    path(
        "admins/sign-out/",
        InstanceAdminSignOutEndpoint.as_view(),
        name="instance-admins",
    ),
    path("admins/<uuid:pk>/", InstanceAdminEndpoint.as_view(), name="instance-admins"),
    path(
        "configurations/",
        InstanceConfigurationEndpoint.as_view(),
        name="instance-configuration",
    ),
    path(
        "configurations/disable-email-feature/",
        DisableEmailFeatureEndpoint.as_view(),
        name="disable-email-configuration",
    ),
    path(
        "admins/sign-in/",
        InstanceAdminSignInEndpoint.as_view(),
        name="instance-admin-sign-in",
    ),
    path(
        "admins/sign-up/",
        InstanceAdminSignUpEndpoint.as_view(),
        name="instance-admin-sign-in",
    ),
    path(
        "admins/sign-up-screen-visited/",
        SignUpScreenVisitedEndpoint.as_view(),
        name="instance-sign-up",
    ),
    path(
        "email-credentials-check/",
        EmailCredentialCheckEndpoint.as_view(),
        name="email-credential-check",
    ),
    path(
        "workspace-slug-check/",
        InstanceWorkSpaceAvailabilityCheckEndpoint.as_view(),
        name="instance-workspace-availability",
    ),
    path("workspaces/", InstanceWorkSpaceEndpoint.as_view(), name="instance-workspace"),
    path(
        "notification-channel/",
        NotificationChannelConfigEndpoint.as_view(),
        name="notification-channel",
    ),
    path(
        "notification-channel/telegram/check/",
        TelegramCheckEndpoint.as_view(),
        name="notification-channel-telegram-check",
    ),
    path(
        "notification-channel/telegram/test/",
        TelegramTestEndpoint.as_view(),
        name="notification-channel-telegram-test",
    ),
    path(
        "notification-channel/whatsapp/status/",
        WhatsAppStatusEndpoint.as_view(),
        name="notification-channel-whatsapp-status",
    ),
    path(
        "notification-channel/whatsapp/connect/",
        WhatsAppConnectEndpoint.as_view(),
        name="notification-channel-whatsapp-connect",
    ),
    path(
        "notification-channel/whatsapp/logout/",
        WhatsAppLogoutEndpoint.as_view(),
        name="notification-channel-whatsapp-logout",
    ),
    path(
        "notification-channel/whatsapp/test/",
        WhatsAppTestEndpoint.as_view(),
        name="notification-channel-whatsapp-test",
    ),
    path(
        "notification-channel/delivery-log/",
        NotificationDeliveryLogEndpoint.as_view(),
        name="notification-channel-delivery-log",
    ),
]
