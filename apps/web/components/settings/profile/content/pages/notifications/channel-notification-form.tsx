/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import { setToast } from "@plane/blocks/toast";
import { Switch } from "@makeplane/propel/components/switch";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Button } from "@makeplane/propel/components/button";
import { ProfileSettingsHeading } from "@/components/settings/profile/heading";
import { notificationChannelService } from "@/services/notification-channel.service";

type Props = {};

const KNOWN_ERRORS = new Set([
  "invalid_phone",
  "invalid_code",
  "code_expired",
  "too_many_attempts",
  "wait_before_resending",
  "start_message_not_found",
  "link_expired",
  "channel_unavailable",
]);

export const ChannelNotificationsForm = observer(function ChannelNotificationsForm(_props: Props) {
  const { t } = useTranslation();
  const { data, mutate } = useSWR("USER_NOTIFICATION_CHANNELS", () => notificationChannelService.list());

  const [awaitingTelegram, setAwaitingTelegram] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");

  const handleError = (err: unknown) => {
    const errorCode = (err as { error?: string } | undefined)?.error ?? "";
    const key = KNOWN_ERRORS.has(errorCode) ? errorCode : "generic";
    setToast({
      type: "error",
      title: t("notification.channels.errors." + key),
    });
  };

  const handleUpdate = async (channel: string, enabled: boolean, events?: string[]) => {
    try {
      await notificationChannelService.update(channel, { enabled, events });
      await mutate();
      setToast({
        type: "success",
        title: t("notification.channels.toast.saved"),
        message: t("notification.channels.toast.saved"),
      });
    } catch (err) {
      handleError(err);
    }
  };

  const handleUnlink = async (channel: string) => {
    try {
      await notificationChannelService.unlink(channel);
      await mutate();
      setToast({
        type: "success",
        title: t("notification.channels.toast.unlinked"),
        message: t("notification.channels.toast.unlinked"),
      });
    } catch (err) {
      handleError(err);
    }
  };

  const handleLinkTelegram = async () => {
    try {
      const r = await notificationChannelService.linkTelegram();
      window.open(r.deep_link, "_blank", "noopener,noreferrer");
      setAwaitingTelegram(true);
    } catch (err) {
      handleError(err);
    }
  };

  const handleVerifyTelegram = async () => {
    try {
      await notificationChannelService.verifyTelegram();
      setAwaitingTelegram(false);
      await mutate();
      setToast({
        type: "success",
        title: t("notification.channels.toast.linked"),
        message: t("notification.channels.toast.linked"),
      });
    } catch (err) {
      handleError(err);
    }
  };

  const handleSendWhatsappCode = async () => {
    try {
      await notificationChannelService.linkWhatsapp(phone);
      setCodeSent(true);
      setToast({
        type: "success",
        title: t("notification.channels.toast.code_sent"),
        message: t("notification.channels.toast.code_sent"),
      });
    } catch (err) {
      handleError(err);
    }
  };

  const handleVerifyWhatsapp = async () => {
    try {
      await notificationChannelService.verifyWhatsapp(code);
      setCodeSent(false);
      setCode("");
      await mutate();
      setToast({
        type: "success",
        title: t("notification.channels.toast.linked"),
        message: t("notification.channels.toast.linked"),
      });
    } catch (err) {
      handleError(err);
    }
  };

  if (!data) return null;

  const renderChannelBlock = (ch: (typeof data.channels)[number]) => {
    const statusKey = !ch.available ? "unavailable" : ch.linked ? "linked" : ch.pending ? "pending" : "not_linked";

    if (!ch.available) {
      return (
        <div key={ch.channel} className="space-y-3 rounded border border-subtle-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium">{t("notification.channels." + ch.channel)}</span>
            <span className="text-danger text-body-xs-regular">{t("notification.channels.status." + statusKey)}</span>
          </div>
        </div>
      );
    }

    if (ch.linked) {
      return (
        <div key={ch.channel} className="space-y-3 rounded border border-subtle-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium">{t("notification.channels." + ch.channel)}</span>
            <span className="text-body-xs-regular text-tertiary">
              {t("notification.channels.status.linked", { address: ch.address })}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              size="sm"
              checked={ch.enabled}
              onCheckedChange={(v) => {
                void handleUpdate(ch.channel, v);
              }}
              aria-label={t("notification.channels.enable")}
            />
            <span className="text-body-xs-regular text-tertiary">{t("notification.channels.enable")}</span>
          </div>
          <p className="text-body-xs-regular text-tertiary">{t("notification.channels.consent")}</p>
          {ch.enabled && data.available_events.length > 0 && (
            <div className="flex flex-col gap-y-1">
              {data.available_events.map((ev) => {
                const checked = ch.events.length === 0 || ch.events.includes(ev);
                return (
                  <div key={ev} className="flex items-center gap-2">
                    <Switch
                      size="sm"
                      checked={checked}
                      onCheckedChange={(v) => {
                        const base = ch.events.length ? ch.events : data.available_events;
                        const nova = v ? [...base, ev] : base.filter((e) => e !== ev);
                        void handleUpdate(ch.channel, ch.enabled, nova);
                      }}
                      aria-label={t("notification.channels.event." + ev)}
                    />
                    <span className="text-body-xs-regular">{t("notification.channels.event." + ev)}</span>
                  </div>
                );
              })}
            </div>
          )}
          <div>
            <Button
              stretch="auto"
              variant="secondary"
              size="md"
              label={t("notification.channels.unlink")}
              onClick={() => void handleUnlink(ch.channel)}
            />
          </div>
        </div>
      );
    }

    if (ch.channel === "telegram") {
      return (
        <div key={ch.channel} className="space-y-3 rounded border border-subtle-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium">{t("notification.channels.telegram")}</span>
            <span className="text-body-xs-regular text-tertiary">{t("notification.channels.status.not_linked")}</span>
          </div>
          <div>
            <Button
              stretch="auto"
              variant="primary"
              size="md"
              label={t("notification.channels.link_telegram")}
              onClick={() => void handleLinkTelegram()}
            />
          </div>
          <p className="text-body-xs-regular text-tertiary">{t("notification.channels.telegram_hint")}</p>
          {(awaitingTelegram || ch.pending) && (
            <div>
              <Button
                stretch="auto"
                variant="primary"
                size="md"
                label={t("notification.channels.confirm_telegram")}
                onClick={() => void handleVerifyTelegram()}
              />
            </div>
          )}
        </div>
      );
    }

    if (ch.channel === "whatsapp") {
      return (
        <div key={ch.channel} className="space-y-3 rounded border border-subtle-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium">{t("notification.channels.whatsapp")}</span>
            <span className="text-body-xs-regular text-tertiary">{t("notification.channels.status.not_linked")}</span>
          </div>
          {!codeSent && (
            <div className="flex items-end gap-2">
              <InputGroup size="md">
                <Input
                  size="md"
                  placeholder={t("notification.channels.phone_placeholder")}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </InputGroup>
              <Button
                stretch="auto"
                variant="primary"
                size="md"
                label={t("notification.channels.send_code")}
                onClick={() => void handleSendWhatsappCode()}
              />
            </div>
          )}
          {(codeSent || ch.pending) && (
            <div className="flex items-end gap-2">
              <InputGroup size="md">
                <Input
                  size="md"
                  placeholder={t("notification.channels.code_placeholder")}
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </InputGroup>
              <Button
                stretch="auto"
                variant="primary"
                size="md"
                label={t("notification.channels.verify")}
                onClick={() => void handleVerifyWhatsapp()}
              />
            </div>
          )}
        </div>
      );
    }

    return null;
  };

  return (
    <div>
      <ProfileSettingsHeading
        title={t("notification.channels.heading")}
        description={t("notification.channels.description")}
      />
      <div className="mt-4 flex flex-col gap-y-3">{data.channels.map((ch) => renderChannelBlock(ch))}</div>
    </div>
  );
});
