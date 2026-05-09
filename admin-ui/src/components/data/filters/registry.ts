import type { Component } from "vue";
import type { FilterDef } from "./types";
import TextFilter from "./TextFilter.vue";
import SelectFilter from "./SelectFilter.vue";
import BooleanFilter from "./BooleanFilter.vue";
import DateFilter from "./DateFilter.vue";

export const FILTER_COMPONENTS: Record<FilterDef["type"], Component> = {
  text: TextFilter,
  select: SelectFilter,
  boolean: BooleanFilter,
  date: DateFilter,
};
