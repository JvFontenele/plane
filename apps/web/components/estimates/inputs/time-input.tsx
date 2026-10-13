/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { useTranslation } from "@plane/i18n";

type TEstimateTimeInputProps = {
  // value in minutes
  value?: string;
  handleEstimateInputValue: (value: string) => void;
};

// The user types hours (decimals allowed, e.g. 1.5); time estimates are stored in minutes.
export function EstimateTimeInput(props: TEstimateTimeInputProps) {
  const { value, handleEstimateInputValue } = props;
  // local state keeps partial input like "1." intact while typing
  const [hours, setHours] = useState(() => (value ? String(Number(value) / 60) : ""));

  // i18n
  const { t } = useTranslation();

  const handleChange = (input: string) => {
    setHours(input);
    const normalized = input.replace(",", ".");
    handleEstimateInputValue(normalized === "" ? "" : String(Math.round(Number(normalized) * 60)));
  };

  return (
    <div className="flex w-full items-center">
      <input
        value={hours}
        onChange={(e) => handleChange(e.target.value)}
        className="w-full border-none bg-transparent px-2 py-2 text-13 focus:border-0 focus:ring-0 focus:outline-none"
        placeholder={t("project_settings.estimates.create.enter_estimate_point")}
        // oxlint-disable-next-line jsx_a11y/no-autofocus
        autoFocus
        inputMode="decimal"
      />
      <span className="pr-2 text-13 text-tertiary">h</span>
    </div>
  );
}
