/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState, useEffect } from "react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { NotificationChannelService } from "@plane/services";
import type { TNotificationChannelConfig, TNotificationChannelConfigUpdate } from "@plane/services";
// blocks
import { setToast } from "@plane/blocks/toast";

type Props = {
  config: TNotificationChannelConfig;
  onSaved: () => void;
};

const service = new NotificationChannelService();

export function WhatsAppSection({ config, onSaved }: Props) {
  const [providerUrl, setProviderUrl] = useState(config.whatsapp.provider_url);
  const [apiKey, setApiKey] = useState("");
  const [instanceName, setInstanceName] = useState(config.whatsapp.instance_name);
  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [qr, setQr] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [testNumber, setTestNumber] = useState("");

  const handleToggle = async (checked: boolean) => {
    await service.updateConfig({ ENABLE_WHATSAPP_NOTIFICATIONS: checked ? "1" : "0" });
    onSaved();
  };

  const handleSave = async () => {
    if (!providerUrl.trim()) return;
    if (!providerUrl.trim().match(/^https?:\/\//)) {
      setToast({ type: "error", title: "Invalid URL", message: "Provider URL must start with http:// or https://" });
      return;
    }
    setSaving(true);
    try {
      const data: TNotificationChannelConfigUpdate = {
        WHATSAPP_PROVIDER_URL: providerUrl.trim(),
        WHATSAPP_INSTANCE_NAME: instanceName.trim(),
      };
      if (apiKey) {
        data.WHATSAPP_API_KEY = apiKey;
      }
      await service.updateConfig(data);
      setApiKey("");
      onSaved();
      setToast({ type: "success", title: "Settings saved", message: "WhatsApp configuration updated." });
    } catch (error) {
      const err = error as { error?: string } | undefined;
      setToast({ type: "error", title: "Error", message: err?.error || "Failed to save settings." });
    } finally {
      setSaving(false);
    }
  };

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const res = await service.connectWhatsapp();
      setQr(res.qr_base64);
      if (res.pairing_code) {
        setPairingCode(res.pairing_code);
      }
      setToast({ type: "success", title: "QR code generated", message: "Scan with WhatsApp → Linked devices." });
    } catch (error) {
      const err = error as { error?: string } | undefined;
      setToast({ type: "error", title: "Connection failed", message: err?.error || "Could not connect." });
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await service.logoutWhatsapp();
      refreshStatus();
      setToast({ type: "success", title: "Disconnected", message: "WhatsApp session logged out." });
    } catch (error) {
      const err = error as { error?: string } | undefined;
      setToast({ type: "error", title: "Disconnect failed", message: err?.error || "Could not disconnect." });
    } finally {
      setDisconnecting(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      await service.testWhatsapp(testNumber);
      setToast({ type: "success", title: "Test sent", message: "Test message sent successfully." });
    } catch (error) {
      const err = error as { error?: string } | undefined;
      if (err?.error === "invalid_number") {
        setToast({ type: "error", title: "Invalid number", message: "Use international format, e.g. +5511999998888" });
      } else {
        setToast({ type: "error", title: "Test failed", message: err?.error || "Could not send test message." });
      }
    } finally {
      setTesting(false);
    }
  };

  const { data: status, mutate: refreshStatus } = useSWR("WHATSAPP_STATUS", () => service.whatsappStatus(), {
    refreshInterval: qr ? 5000 : 0,
  });

  useEffect(() => {
    if (status?.state === "open") {
      setQr(null);
      setPairingCode(null);
    }
  }, [status?.state]);

  const statusLabel = () => {
    if (!status) return "Loading...";
    if (status.error) return `Error: ${status.error}`;
    switch (status.state) {
      case "not_configured":
        return "Not configured";
      case "open":
        return "Connected";
      case "connecting":
        return "Waiting for pairing";
      case "close":
        return "Disconnected";
      default:
        return status.state;
    }
  };

  return (
    <div>
      <h3 className="text-base font-semibold">WhatsApp</h3>
      <p className="mt-1 text-13 text-tertiary">
        Uses a self-hosted Evolution API instance (unofficial, based on WhatsApp Web). One sender number is shared by
        the whole instance. The number may be banned by WhatsApp if used for bulk messaging.
      </p>

      <div className="mt-4 flex items-center gap-3">
        <Switch
          aria-label="Enable WhatsApp"
          checked={config.whatsapp.enabled}
          onCheckedChange={handleToggle}
          size="sm"
        />
        <span className="text-13">Enable WhatsApp</span>
      </div>

      <div className="mt-4 space-y-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="nc-provider-url" className="text-13 font-medium text-secondary">
            Provider URL
          </label>
          <InputGroup size="md">
            <Input
              id="nc-provider-url"
              placeholder="http://evolution-api:8080"
              value={providerUrl}
              onChange={(e) => setProviderUrl(e.target.value)}
              size="md"
              aria-label="Provider URL"
            />
          </InputGroup>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="nc-api-key" className="text-13 font-medium text-secondary">
            API key
          </label>
          <InputGroup size="md">
            <Input
              id="nc-api-key"
              type="password"
              placeholder={
                config.whatsapp.api_key_set ? "Key saved — type to replace" : "Evolution AUTHENTICATION_API_KEY"
              }
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              size="md"
              aria-label="API key"
            />
          </InputGroup>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="nc-instance-name" className="text-13 font-medium text-secondary">
            Instance name
          </label>
          <InputGroup size="md">
            <Input
              id="nc-instance-name"
              placeholder="Instance name"
              value={instanceName}
              onChange={(e) => setInstanceName(e.target.value)}
              size="md"
              aria-label="Instance name"
            />
          </InputGroup>
        </div>
        <Button
          stretch="auto"
          variant="primary"
          size="md"
          label="Save"
          loading={saving}
          disabled={!providerUrl.trim()}
          onClick={handleSave}
        />
      </div>

      <div className="mt-4 flex items-center gap-3">
        <span className="text-13">{statusLabel()}</span>
        {status?.state === "open" && (
          <Button
            stretch="auto"
            variant="secondary"
            size="md"
            label="Disconnect"
            loading={disconnecting}
            disabled={disconnecting}
            onClick={handleDisconnect}
          />
        )}
        <Button
          stretch="auto"
          variant="secondary"
          size="md"
          label="Connect"
          loading={connecting}
          disabled={connecting}
          onClick={handleConnect}
        />
      </div>

      {qr && (
        <div className="mt-4 flex flex-col items-center gap-2">
          <img
            src={qr.startsWith("data:") ? qr : `data:image/png;base64,${qr}`}
            alt="WhatsApp pairing QR code"
            className="size-56"
          />
          <p className="text-center text-13">
            Scan with WhatsApp → Linked devices. The code expires quickly; click Connect again for a new one.
            {pairingCode && <> Pairing code: {pairingCode}</>}
          </p>
        </div>
      )}

      <div className="mt-4 flex items-end gap-3">
        <div className="flex-1">
          <label htmlFor="nc-test-number" className="text-13 font-medium text-secondary">
            Test number
          </label>
          <InputGroup size="md">
            <Input
              id="nc-test-number"
              placeholder="+5511999998888"
              value={testNumber}
              onChange={(e) => setTestNumber(e.target.value)}
              size="md"
              aria-label="Test number"
            />
          </InputGroup>
        </div>
        <Button
          stretch="auto"
          variant="secondary"
          size="md"
          label="Send test"
          loading={testing}
          disabled={testing || !testNumber.trim()}
          onClick={handleTest}
        />
      </div>
    </div>
  );
}
