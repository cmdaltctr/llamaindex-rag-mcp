/* Subset of the real operation catalogue (`build_operation_catalogue().describe(...)`), captured 2026-10-13. */
import type { OperationDescriptor } from "../../api/pipelines";
import { CATALOGUE_PART_ONE } from "./catalogueOne";
import { CATALOGUE_PART_TWO } from "./catalogueTwo";

export const CATALOGUE: OperationDescriptor[] = [...CATALOGUE_PART_ONE, ...CATALOGUE_PART_TWO];
