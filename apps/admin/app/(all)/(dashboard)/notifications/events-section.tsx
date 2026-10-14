/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
// plane imports
import { Switch } from "@makeplane/propel/components/switch";
import { NotificationChannelService } from "@plane/services";
import type { TNotificationChannelConfig } from "@plane/services";
// blocks
import { setToast } from "@plane/blocks/toast";

type Props = {
  config: TNotificationChannelConfig;
  onSaved: () => void;
};

const LABELS: Record<string, string> = {
  state_change: "State changes",
  issue_completed: "Work item completed",
  comment: "Comments",
  mention: "Mentions",
  property_change: "Other property changes (title, description, assignees, priority, dates…)",
};

const service = new NotificationChannelService();

export function EventsSection({ config, onSaved }: Props) {
  const { data: deliveryLog } = useSWR("NOTIFICATION_DELIVERY_LOG", () => service.deliveryLog());

  const handleEventToggle = async (event: string) => {
    const currentList = config.events.split(",").filter(Boolean);
    const newList = currentList.includes(event) ? currentList.filter((e) => e !== event) : [...currentList, event];
    await service.updateConfig({ NOTIFICATION_CHANNEL_EVENTS: newList });
    onSaved();
    setToast({ type: "success", title: "Events updated", message: "Notification event types saved." });
  };

  return (
    <div>
      <h3 className="text-base font-semibold">Events</h3>
      <p className="mt-1 text-13 text-tertiary">
        Event types that may be delivered through external channels. Users can narrow this further.
      </p>

      <div className="mt-4 space-y-3">
        {config.available_events.map((ev) => (
          <div key={ev} className="flex items-center gap-3">
            <Switch
              aria-label={`Enable ${LABELS[ev] || ev}`}
              checked={config.events.split(",").includes(ev)}
              onCheckedChange={() => handleEventToggle(ev)}
              size="sm"
            />
            <span className="text-13">{LABELS[ev] || ev}</span>
          </div>
        ))}
      </div>

      <div className="mt-8">
        <h4 className="text-sm font-medium">Recent delivery problems</h4>
        {deliveryLog && deliveryLog.length > 0 ? (
          <div className="mt-2 overflow-x-auto">
            <table className="min-w-full text-13">
              <thead>
                <tr className="border-b">
                  <th className="pb-2 text-left font-medium">Channel</th>
                  <th className="pb-2 text-left font-medium">Status</th>
                  <th className="pb-2 text-left font-medium">Reason</th>
                  <th className="pb-2 text-left font-medium">Attempts</th>
                  <th className="pb-2 text-left font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {deliveryLog.map((log) => (
                  <tr key={log.id} className="border-b last:border-b-0">
                    <td className="py-2">{log.channel}</td>
                    <td className="py-2">{log.status}</td>
                    <td className="py-2">{log.reason}</td>
                    <td className="py-2">{log.attempts}</td>
                    <td className="py-2">{log.created_at ? new Date(log.created_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-2 text-13 text-tertiary">No failed or skipped deliveries.</p>
        )}
      </div>
    </div>
  );
}
