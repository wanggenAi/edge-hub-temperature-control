export type RunbookModuleKey =
  | "offline_model_quality"
  | "evidence_confidence"
  | "online_usefulness"
  | "runtime_influence"
  | "feature_drift"
  | "label_drift"
  | "runtime_reliability_fallback"
  | "dangerous_class_recall";

export type RunbookManifestEntry = {
  key: RunbookModuleKey;
  title: string;
  section: string;
  tags: string[];
};

export const AI_OPS_RUNBOOK_REGISTRY: Record<RunbookModuleKey, RunbookManifestEntry> = {
  offline_model_quality: {
    key: "offline_model_quality",
    title: "Offline Model Quality",
    section: "offline",
    tags: ["macro-f1", "artifact", "dangerous-recall"],
  },
  evidence_confidence: {
    key: "evidence_confidence",
    title: "Evidence Confidence",
    section: "summary",
    tags: ["sample-size", "freshness", "confidence"],
  },
  online_usefulness: {
    key: "online_usefulness",
    title: "Online Usefulness",
    section: "online",
    tags: ["ai-vs-manual", "outcomes", "evidence"],
  },
  runtime_influence: {
    key: "runtime_influence",
    title: "Runtime Influence",
    section: "runtime",
    tags: ["ranking", "rule_center", "influence"],
  },
  feature_drift: {
    key: "feature_drift",
    title: "Feature Drift",
    section: "drift",
    tags: ["distribution-shift", "features", "baseline-vs-live"],
  },
  label_drift: {
    key: "label_drift",
    title: "Label Drift",
    section: "drift",
    tags: ["labeling", "distribution-shift", "evidence"],
  },
  runtime_reliability_fallback: {
    key: "runtime_reliability_fallback",
    title: "Runtime Reliability / Fallback",
    section: "runtime",
    tags: ["fallback", "runtime-health", "availability"],
  },
  dangerous_class_recall: {
    key: "dangerous_class_recall",
    title: "Dangerous-Class Recall",
    section: "offline",
    tags: ["worse", "high", "risk"],
  },
};
