/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { NotificationChannelService } from "@plane/services";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
import { Skeleton } from "@/components/common/skeleton";
// types
import type { Route } from "./+types/page";
// local
import { TelegramSection } from "./telegram-section";
import { WhatsAppSection } from "./whatsapp-section";
import { EventsSection } from "./events-section";

const service = new NotificationChannelService();

const InstanceNotificationsPage = observer(function InstanceNotificationsPage(_props: Route.ComponentProps) {
  const { data, mutate } = useSWR("NOTIFICATION_CHANNEL_CONFIG", () => service.config());

  return (
    <PageWrapper
      header={{
        title: "Notifications",
        description:
          "Send work item notifications through Telegram and WhatsApp. Users still need to link their accounts and opt in.",
      }}
    >
      {!data ? (
        <Skeleton className="space-y-10">
          <Skeleton.Item height="50px" width="75%" />
          <Skeleton.Item height="50px" width="75%" />
          <Skeleton.Item height="50px" width="40%" />
          <Skeleton.Item height="50px" width="40%" />
          <Skeleton.Item height="50px" width="20%" />
        </Skeleton>
      ) : (
        <div className="space-y-10">
          <TelegramSection config={data} onSaved={mutate} />
          <WhatsAppSection config={data} onSaved={mutate} />
          <EventsSection config={data} onSaved={mutate} />
        </div>
      )}
    </PageWrapper>
  );
});

export const meta: Route.MetaFunction = () => [{ title: "Notifications Settings - God Mode" }];

export default InstanceNotificationsPage;
