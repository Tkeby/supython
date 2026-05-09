export type FilterValue = string | number | boolean | null;

export type FilterValues = Record<string, FilterValue>;

export interface FilterOption {
  label: string;
  value: FilterValue;
}

export type FilterDef =
  | {
      type: "text";
      key: string;
      label?: string;
      placeholder?: string;
      debounceMs?: number;
      width?: number | string;
    }
  | {
      type: "select";
      key: string;
      label?: string;
      options: FilterOption[];
      placeholder?: string;
      clearable?: boolean;
      width?: number | string;
    }
  | {
      type: "boolean";
      key: string;
      label?: string;
      trueLabel?: string;
      falseLabel?: string;
      anyLabel?: string;
      width?: number | string;
    }
  | {
      type: "date";
      key: string;
      label?: string;
      placeholder?: string;
      width?: number | string;
    };
