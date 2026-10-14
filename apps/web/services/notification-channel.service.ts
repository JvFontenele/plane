/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TUserNotificationChannel = {
  channel: "telegram" | "whatsapp";
  available: boolean;
  linked: boolean;
  address: string;
  enabled: boolean;
  consented_at: string | null;
  events: string[];
  pending: boolean;
};

export type TUserNotificationChannels = {
  channels: TUserNotificationChannel[];
  available_events: string[];
  telegram_bot_username: string;
};

export class NotificationChannelService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  base = "/api/users/me/notification-channels/";

  async list(): Promise<TUserNotificationChannels> {
    return this.get(this.base)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async update(
    channel: string,
    data: Partial<{ enabled: boolean; events: string[] }>
  ): Promise<TUserNotificationChannel> {
    return this.patch(`${this.base}${channel}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async unlink(channel: string): Promise<void> {
    return this.delete(`${this.base}${channel}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async linkTelegram(): Promise<{ deep_link: string; expires_at: string }> {
    return this.post(`${this.base}telegram/link/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async verifyTelegram(): Promise<TUserNotificationChannel> {
    return this.post(`${this.base}telegram/verify/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async linkWhatsapp(phone: string): Promise<{ sent: boolean }> {
    return this.post(`${this.base}whatsapp/link/`, { phone })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async verifyWhatsapp(code: string): Promise<TUserNotificationChannel> {
    return this.post(`${this.base}whatsapp/verify/`, { code })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

export const notificationChannelService = new NotificationChannelService();

export default notificationChannelService;
