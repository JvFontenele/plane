/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { NotificationChannelService } from "@plane/services";
import type { TNotificationChannelConfig } from "@plane/services";
// blocks
import { setToast } from "@plane/blocks/toast";

type Props = {
  config: TNotificationChannelConfig;
  onSaved: () => void;
};

const service = new NotificationChannelService();

export function TelegramSection({ config, onSaved }: Props) {
  const [token, setToken] = useState("");
  const [savingToken, setSavingToken] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [testing, setTesting] = useState(false);

  const handleToggle = async (checked: boolean) => {
    await service.updateConfig({ ENABLE_TELEGRAM_NOTIFICATIONS: checked ? "1" : "0" });
    onSaved();
  };

  const handleSaveToken = async () => {
    if (!token.trim()) return;
    setSavingToken(true);
    try {
      await service.updateConfig({ TELEGRAM_BOT_TOKEN: token.trim() });
      setToken("");
      onSaved();
      setToast({ type: "success", title: "Token saved", message: "Telegram bot token updated." });
    } catch (error) {
      const err = error as { error?: string } | undefined;
      setToast({ type: "error", title: "Error", message: err?.error || "Failed to save token." });
    } finally {
      setSavingToken(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    try {
      await service.checkTelegram();
      onSaved();
      setToast({ type: "success", title: "Bot verified", message: "Telegram bot configuration is valid." });
    } catch (error) {
      const err = error as { error?: string } | undefined;
      setToast({ type: "error", title: "Verification failed", message: err?.error || "Could not verify bot." });
    } finally {
      setVerifying(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      await service.testTelegram();
      setToast({ type: "success", title: "Test sent", message: "Test message sent to your Telegram." });
    } catch (error) {
      const err = error as { error?: string } | undefined;
      if (err?.error === "link_your_account_first") {
        setToast({
          type: "error",
          title: "Account not linked",
          message: "Link your own Telegram in account settings first.",
        });
      } else {
        setToast({ type: "error", title: "Test failed", message: err?.error || "Could not send test message." });
      }
    } finally {
      setTesting(false);
    }
  };

  return (
    <div>
      <h3 className="text-base font-semibold">Telegram</h3>
      <p className="mt-1 text-13 text-tertiary">
        Create a bot with @BotFather and paste its token. The token is stored encrypted and never shown again.
      </p>

      <div className="mt-4 flex items-center gap-3">
        <Switch
          aria-label="Enable Telegram"
          checked={config.telegram.enabled}
          onCheckedChange={handleToggle}
          size="sm"
        />
        <span className="text-13">Enable Telegram</span>
      </div>

      <div className="mt-4 flex items-end gap-3">
        <div className="flex-1">
          <label htmlFor="nc-bot-token" className="text-13 font-medium text-secondary">
            Bot token
          </label>
          <InputGroup size="md">
            <Input
              id="nc-bot-token"
              type="password"
              placeholder={config.telegram.token_set ? "Token saved — type to replace" : "123456:ABC-DEF..."}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              size="md"
              aria-label="Telegram bot token"
            />
          </InputGroup>
        </div>
        <Button
          stretch="auto"
          variant="primary"
          size="md"
          label="Save token"
          loading={savingToken}
          disabled={!token.trim()}
          onClick={handleSaveToken}
        />
      </div>

      <div className="mt-2 text-13">
        {config.telegram.token_set
          ? config.telegram.bot_username
            ? `Connected as @${config.telegram.bot_username}`
            : "Token saved, not verified"
          : "Not configured"}
      </div>

      <div className="mt-4 flex gap-3">
        <Button
          stretch="auto"
          variant="secondary"
          size="md"
          label="Verify bot"
          loading={verifying}
          onClick={handleVerify}
        />
        <Button
          stretch="auto"
          variant="secondary"
          size="md"
          label="Send test message"
          loading={testing}
          onClick={handleTest}
        />
      </div>
    </div>
  );
}
