import bundle from "../../../../../contracts/training-center/examples.json";
import type { ApiErrorBody, DatasetOverviewResponse, DatasetsResponse, FilesResponse, FormatStatsResponse, LineageGraph, OverviewResponse, SamplesResponse, Scope } from "../../contracts/training-center";

// This JSON is validated against Pydantic and regenerated in the contract checks.
// Never import it from production pages: client.ts loads the interceptor only in explicit DEV mode.
export type Scenario = "success" | "empty";
export const fixtureProvenance = bundle.provenance;
export const cases = (scenario: Scenario) => bundle.scenarios[scenario].responses;
export const overview = (scenario: Scenario) => cases(scenario).overview.body as OverviewResponse;
export const files = (scenario: Scenario) => cases(scenario).files.body as FilesResponse;
export const datasets = (scenario: Scenario) => cases(scenario).datasets.body as DatasetsResponse;
export const stats = (scenario: Scenario) => cases(scenario).txt_stats.body as FormatStatsResponse;
export const graph = (scenario: Scenario) => cases(scenario).graph.body as LineageGraph;
export const datasetOverview = (scenario: Scenario, kind: "cpt" | "sft" | "dpo") => cases(scenario)[`${kind}_overview`].body as DatasetOverviewResponse;
export const samples = (scenario: Scenario) => {
  const responses = cases(scenario);
  const pages = [responses.cpt_samples, responses.cpt_samples_next, responses.sft_samples, responses.dpo_samples];
  return pages.flatMap(page => (page.body as SamplesResponse).items);
};
export const fixtureScope = (scenario: Scenario): Scope => overview(scenario).scope;
export const errors = bundle.scenarios.error.responses as Record<string, { status_code: number; body: ApiErrorBody }>;
