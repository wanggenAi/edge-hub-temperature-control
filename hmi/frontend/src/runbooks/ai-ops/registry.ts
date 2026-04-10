import dangerousClassRecallMd from "./dangerous-class-recall.md?raw";
import evidenceConfidenceMd from "./evidence-confidence.md?raw";
import featureDriftMd from "./feature-drift.md?raw";
import labelDriftMd from "./label-drift.md?raw";
import offlineModelQualityMd from "./offline-model-quality.md?raw";
import onlineUsefulnessMd from "./online-usefulness.md?raw";
import runtimeInfluenceMd from "./runtime-influence.md?raw";
import runtimeReliabilityMd from "./runtime-reliability.md?raw";

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
  markdown: string;
};

export const AI_OPS_RUNBOOK_REGISTRY: Record<RunbookModuleKey, RunbookManifestEntry> = {
  offline_model_quality: {
    key: "offline_model_quality",
    title: "Offline Model Quality",
    section: "offline",
    tags: ["macro-f1", "artifact", "dangerous-recall"],
    markdown: offlineModelQualityMd,
  },
  evidence_confidence: {
    key: "evidence_confidence",
    title: "Evidence Confidence",
    section: "summary",
    tags: ["sample-size", "freshness", "confidence"],
    markdown: evidenceConfidenceMd,
  },
  online_usefulness: {
    key: "online_usefulness",
    title: "Online Usefulness",
    section: "online",
    tags: ["ai-vs-manual", "outcomes", "evidence"],
    markdown: onlineUsefulnessMd,
  },
  runtime_influence: {
    key: "runtime_influence",
    title: "Runtime Influence",
    section: "runtime",
    tags: ["ranking", "rule_center", "influence"],
    markdown: runtimeInfluenceMd,
  },
  feature_drift: {
    key: "feature_drift",
    title: "Feature Drift",
    section: "drift",
    tags: ["distribution-shift", "features", "baseline-vs-live"],
    markdown: featureDriftMd,
  },
  label_drift: {
    key: "label_drift",
    title: "Label Drift",
    section: "drift",
    tags: ["labeling", "distribution-shift", "evidence"],
    markdown: labelDriftMd,
  },
  runtime_reliability_fallback: {
    key: "runtime_reliability_fallback",
    title: "Runtime Reliability / Fallback",
    section: "runtime",
    tags: ["fallback", "runtime-health", "availability"],
    markdown: runtimeReliabilityMd,
  },
  dangerous_class_recall: {
    key: "dangerous_class_recall",
    title: "Dangerous-Class Recall",
    section: "offline",
    tags: ["worse", "high", "risk"],
    markdown: dangerousClassRecallMd,
  },
};
