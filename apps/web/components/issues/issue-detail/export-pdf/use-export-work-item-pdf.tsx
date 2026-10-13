/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { pdf } from "@react-pdf/renderer";
// plane imports
import { useTranslation } from "@plane/i18n";
import { setToast } from "@plane/blocks/toast";
import type { TIssue } from "@plane/types";
import { EEstimateSystem } from "@plane/types";
import { convertMinutesToHoursMinutesString, renderFormattedDate } from "@plane/utils";
// hooks
import { useProjectEstimates } from "@/hooks/store/estimates";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
import { useProjectState } from "@/hooks/store/use-project-state";
import { useParseEditorContent } from "@/hooks/use-parse-editor-content";
// local imports
import type { TWorkItemReportRow } from "./document";
import { WorkItemReportPDF } from "./document";

const EMPTY_VALUE = "-";

const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export const useExportWorkItemPdf = (workspaceSlug: string, issue: TIssue) => {
  const [isExporting, setIsExporting] = useState(false);
  // store hooks
  const { t } = useTranslation();
  const {
    fetchSubIssues,
    subIssues: { subIssuesByIssueId },
    issue: { getIssueById },
  } = useIssueDetail();
  const { getStateById } = useProjectState();
  const { getUserDetails } = useMember();
  const { getProjectById } = useProject();
  const { getProjectEstimates, currentActiveEstimateIdByProjectId, getEstimateById } = useProjectEstimates();
  const { replaceCustomComponentsFromHTMLContent } = useParseEditorContent({
    projectId: issue.project_id ?? undefined,
    workspaceSlug,
  });

  const exportPdf = async () => {
    const projectId = issue.project_id;
    if (!projectId || isExporting) return;
    setIsExporting(true);
    try {
      await Promise.all([
        fetchSubIssues(workspaceSlug, projectId, issue.id),
        getProjectEstimates(workspaceSlug, projectId),
      ]);

      const project = getProjectById(projectId);
      const activeEstimateId = currentActiveEstimateIdByProjectId(projectId);
      const estimate = activeEstimateId ? getEstimateById(activeEstimateId) : undefined;
      const isNumericEstimate = estimate?.type === EEstimateSystem.TIME || estimate?.type === EEstimateSystem.POINTS;

      const getEstimateValue = (estimatePointId: string | null) =>
        estimatePointId ? estimate?.estimatePointById(estimatePointId)?.value : undefined;
      const formatEstimate = (value: number | string | undefined) => {
        if (value === undefined || value === "") return EMPTY_VALUE;
        return estimate?.type === EEstimateSystem.TIME
          ? convertMinutesToHoursMinutesString(Number(value)).trim() || "0h"
          : String(value);
      };
      const formatAssignees = (item: TIssue) =>
        item.assignee_ids
          .map((id) => getUserDetails(id)?.display_name)
          .filter(Boolean)
          .join(", ") || EMPTY_VALUE;
      const getIdentifier = (item: TIssue) =>
        `${getProjectById(item.project_id)?.identifier ?? project?.identifier ?? ""}-${item.sequence_id}`;

      const subIssues = (subIssuesByIssueId(issue.id) ?? [])
        .map((id) => getIssueById(id))
        .filter((item): item is TIssue => !!item);
      const isCompleted = (item: TIssue) => getStateById(item.state_id)?.group === "completed";

      const subItems: TWorkItemReportRow[] = subIssues.map((item) => ({
        identifier: getIdentifier(item),
        name: item.name,
        state: getStateById(item.state_id)?.name ?? EMPTY_VALUE,
        assignees: formatAssignees(item),
        estimate: formatEstimate(getEstimateValue(item.estimate_point)),
      }));

      // estimate totals only make sense for numeric estimate systems
      const sumEstimates = (items: TIssue[]) =>
        items.reduce((total, item) => total + (Number(getEstimateValue(item.estimate_point)) || 0), 0);
      const completedSubIssues = subIssues.filter(isCompleted);
      const summary = [
        {
          label: t("issue.export_pdf.progress"),
          value: `${completedSubIssues.length}/${subIssues.length}`,
        },
        ...(isNumericEstimate
          ? [
              { label: t("issue.export_pdf.total_estimate"), value: formatEstimate(sumEstimates(subIssues)) },
              {
                label: t("issue.export_pdf.completed_estimate"),
                value: formatEstimate(sumEstimates(completedSubIssues)),
              },
            ]
          : []),
      ];

      const descriptionHtml = issue.description_html?.trim()
        ? await replaceCustomComponentsFromHTMLContent({ htmlContent: issue.description_html })
        : "";
      const identifier = getIdentifier(issue);

      const blob = await pdf(
        <WorkItemReportPDF
          data={{
            title: issue.name,
            subtitle: `${project?.name ?? ""} · ${identifier}`,
            generatedOn: t("issue.export_pdf.generated_on", { date: renderFormattedDate(new Date()) ?? "" }),
            descriptionHtml,
            properties: [
              { label: t("state"), value: getStateById(issue.state_id)?.name ?? EMPTY_VALUE },
              { label: t("assignees"), value: formatAssignees(issue) },
              { label: t("priority"), value: t(issue.priority ?? "none") },
              { label: t("start_date"), value: renderFormattedDate(issue.start_date) ?? EMPTY_VALUE },
              { label: t("due_date"), value: renderFormattedDate(issue.target_date) ?? EMPTY_VALUE },
              { label: t("estimate"), value: formatEstimate(getEstimateValue(issue.estimate_point)) },
            ],
            subItemsTitle: t("common.sub_work_items"),
            columns: {
              identifier: "ID",
              name: t("title"),
              state: t("state"),
              assignees: t("assignees"),
              estimate: t("estimate"),
            },
            subItems,
            summary,
          }}
        />
      ).toBlob();
      downloadBlob(blob, `${identifier}.pdf`);
    } catch (error) {
      console.error("Error exporting work item as PDF", error);
      setToast({ type: "error", title: t("issue.export_pdf.error") });
    } finally {
      setIsExporting(false);
    }
  };

  return { exportPdf, isExporting };
};
