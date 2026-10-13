/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Document, Page, StyleSheet, Text, View } from "@react-pdf/renderer";
import { Html } from "react-pdf-html";
// also registers the Inter font family
import { EDITOR_PDF_DOCUMENT_STYLESHEET } from "@/components/editor/pdf";

export type TWorkItemReportField = { label: string; value: string };

export type TWorkItemReportRow = {
  identifier: string;
  name: string;
  state: string;
  assignees: string;
  estimate: string;
};

export type TWorkItemReportData = {
  title: string;
  subtitle: string;
  generatedOn: string;
  descriptionHtml: string;
  properties: TWorkItemReportField[];
  subItemsTitle: string;
  columns: Record<keyof TWorkItemReportRow, string>;
  subItems: TWorkItemReportRow[];
  summary: TWorkItemReportField[];
};

const COLUMN_WIDTHS: Record<keyof TWorkItemReportRow, string> = {
  identifier: "13%",
  name: "39%",
  state: "16%",
  assignees: "20%",
  estimate: "12%",
};

const COLUMNS = Object.keys(COLUMN_WIDTHS) as (keyof TWorkItemReportRow)[];

const styles = StyleSheet.create({
  page: { backgroundColor: "#ffffff", padding: 40, fontFamily: "Inter", fontSize: 9, color: "#171717" },
  subtitle: { fontSize: 9, color: "#737373", marginBottom: 4 },
  title: { fontSize: 16, fontWeight: "bold", marginBottom: 4 },
  generatedOn: { fontSize: 8, color: "#a3a3a3", marginBottom: 16 },
  sectionTitle: { fontSize: 11, fontWeight: "semibold", marginTop: 16, marginBottom: 6 },
  fieldRow: { flexDirection: "row", paddingVertical: 2 },
  fieldLabel: { width: "25%", color: "#737373" },
  fieldValue: { width: "75%" },
  tableHeader: { flexDirection: "row", backgroundColor: "#f5f5f5", borderBottom: "1px solid #e5e5e5" },
  tableRow: { flexDirection: "row", borderBottom: "1px solid #f0f0f0" },
  headerCell: { padding: 4, fontWeight: "semibold" },
  cell: { padding: 4 },
  summary: { marginTop: 8, alignItems: "flex-end" },
});

function FieldList({ fields }: { fields: TWorkItemReportField[] }) {
  return (
    <View>
      {fields.map((field) => (
        <View key={field.label} style={styles.fieldRow} wrap={false}>
          <Text style={styles.fieldLabel}>{field.label}</Text>
          <Text style={styles.fieldValue}>{field.value}</Text>
        </View>
      ))}
    </View>
  );
}

export function WorkItemReportPDF({ data }: { data: TWorkItemReportData }) {
  return (
    <Document title={`${data.subtitle} ${data.title}`}>
      <Page size="A4" style={styles.page}>
        <Text style={styles.subtitle}>{data.subtitle}</Text>
        <Text style={styles.title}>{data.title}</Text>
        <Text style={styles.generatedOn}>{data.generatedOn}</Text>

        {data.descriptionHtml && <Html stylesheet={EDITOR_PDF_DOCUMENT_STYLESHEET}>{data.descriptionHtml}</Html>}

        <FieldList fields={data.properties} />

        {data.subItems.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>{data.subItemsTitle}</Text>
            <View style={styles.tableHeader} fixed>
              {COLUMNS.map((column) => (
                <Text key={column} style={[styles.headerCell, { width: COLUMN_WIDTHS[column] }]}>
                  {data.columns[column]}
                </Text>
              ))}
            </View>
            {data.subItems.map((row) => (
              <View key={row.identifier} style={styles.tableRow} wrap={false}>
                {COLUMNS.map((column) => (
                  <Text key={column} style={[styles.cell, { width: COLUMN_WIDTHS[column] }]}>
                    {row[column]}
                  </Text>
                ))}
              </View>
            ))}
            <View style={styles.summary}>
              <FieldList fields={data.summary} />
            </View>
          </>
        )}
      </Page>
    </Document>
  );
}
