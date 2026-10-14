/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { API_BASE_URL } from "@plane/constants";
// api service
import { APIService } from "../api.service";

export type TNotificationChannelConfig = {
  telegram: { enabled: boolean; token_set: boolean; bot_username: string };
  whatsapp: { enabled: boolean; provider_url: string; api_key_set: boolean; instance_name: string };
  events: string;
  available_events: string[];
};

export type TNotificationChannelConfigUpdate = Partial<{
  ENABLE_TELEGRAM_NOTIFICATIONS: "0" | "1";
  TELEGRAM_BOT_TOKEN: string;
  ENABLE_WHATSAPP_NOTIFICATIONS: "0" | "1";
  WHATSAPP_PROVIDER_URL: string;
  WHATSAPP_API_KEY: string;
  WHATSAPP_INSTANCE_NAME: string;
  NOTIFICATION_CHANNEL_EVENTS: string[];
}>;

export type TNotificationDeliveryLog = {
  id: string;
  channel: string;
  status: string;
  reason: string;
  attempts: number;
  created_at: string | null;
};

/**
 * Service class for managing notification channel configuration
 * Handles Telegram and WhatsApp channel setup and testing
 * @extends {APIService}
 */
export class NotificationChannelService extends APIService {
  /**
   * Creates an instance of NotificationChannelService
   * Initializes the service with the base API URL
   */
  constructor() {
    super(API_BASE_URL);
  }

  /**
   * Retrieves the current notification channel configuration
   * @returns {Promise<TNotificationChannelConfig>}
   */
  async config(): Promise<TNotificationChannelConfig> {
    return this.get("/api/instances/notification-channel/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Updates the notification channel configuration
   * @param {TNotificationChannelConfigUpdate} data
   * @returns {Promise<TNotificationChannelConfig>}
   */
  async updateConfig(data: TNotificationChannelConfigUpdate): Promise<TNotificationChannelConfig> {
    return this.patch("/api/instances/notification-channel/", data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Checks Telegram bot configuration validity
   * @returns {Promise<{ ok: boolean; bot_username: string }>}
   */
  async checkTelegram(): Promise<{ ok: boolean; bot_username: string }> {
    return this.post("/api/instances/notification-channel/telegram/check/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Sends a test message via Telegram
   * @returns {Promise<{ ok: boolean }>}
   */
  async testTelegram(): Promise<{ ok: boolean }> {
    return this.post("/api/instances/notification-channel/telegram/test/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Retrieves WhatsApp connection status
   * @returns {Promise<{ state: string; error?: string }>}
   */
  async whatsappStatus(): Promise<{ state: string; error?: string }> {
    return this.get("/api/instances/notification-channel/whatsapp/status/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Initiates WhatsApp QR pairing
   * @returns {Promise<{ qr_base64: string; pairing_code: string }>}
   */
  async connectWhatsapp(): Promise<{ qr_base64: string; pairing_code: string }> {
    return this.post("/api/instances/notification-channel/whatsapp/connect/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Logs out and disconnects WhatsApp
   * @returns {Promise<{ ok: boolean }>}
   */
  async logoutWhatsapp(): Promise<{ ok: boolean }> {
    return this.post("/api/instances/notification-channel/whatsapp/logout/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Sends a test message via WhatsApp to the specified number
   * @param {string} number
   * @returns {Promise<{ ok: boolean }>}
   */
  async testWhatsapp(number: string): Promise<{ ok: boolean }> {
    return this.post("/api/instances/notification-channel/whatsapp/test/", { number })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Retrieves the delivery log for notification messages
   * @returns {Promise<TNotificationDeliveryLog[]>}
   */
  async deliveryLog(): Promise<TNotificationDeliveryLog[]> {
    return this.get("/api/instances/notification-channel/delivery-log/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
