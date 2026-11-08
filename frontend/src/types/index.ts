export interface User { id: string; username: string; email: string; role: 'CUSTOMER' | 'ADMIN'; status: string; }
export interface Detector { method: string; score: number; confidence: number; interpretation: string; details: Record<string, any>; }
export interface AnalysisItem { id: string; filename: string; status: string; verdict: string; confidence: number; final_score: number; created_at: string; processing_time_s: number; }
export interface NarrativeSection { title: string; body: string; }
export interface KeyFinding { title: string; detail: string; direction: 'supports_camera' | 'supports_ai' | 'neutral'; strength: number; }
export interface DetectorNote { method: string; title: string; what_it_measures: string; reading: string; interpretation: string; score: number; confidence: number; weight: number; evidence: number; direction: string; applied: boolean; }
export interface Narrative {
  headline: string; summary: string; verdict_label: string;
  final_score: number; confidence: number;
  sections: NarrativeSection[]; key_findings: KeyFinding[]; detector_notes: DetectorNote[];
  next_steps: string[]; confidence_note: string; regions_flagged: number; engine: string;
}
export interface Report { analysis: AnalysisItem; detectors: Detector[]; breakdown: { method: string; label?: string; score: number; confidence?: number; weight: number; contribution: number; calibrated?: number; applied?: boolean; interpretation: string }[]; explanation: string; regions: { id: number; x: number; y: number; width: number; height: number; reason: string }[]; artifacts: Record<string, any>; image_info: Record<string, any>; narrative?: Narrative; report_name?: string; }
export const verdictMeta: Record<string, { label: string; color: string; bg: string }> = {
  LIKELY_REAL: { label: 'Likely Real', color: 'text-green-400', bg: 'border-green-500/30 bg-green-500/10' },
  LIKELY_AI_MANIPULATED: { label: 'Likely AI Generated / Manipulated', color: 'text-red-400', bg: 'border-red-500/30 bg-red-500/10' },
  INCONCLUSIVE: { label: 'Inconclusive', color: 'text-yellow-300', bg: 'border-yellow-500/30 bg-yellow-500/10' },
};
