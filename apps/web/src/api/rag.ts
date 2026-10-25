import { request, type ApiContext } from './client';
export interface GeneratedAnswer {generation_id:string;trace_id:string;status:string;error_code:string|null;result:{answer?:string;citations?:Array<{segment_id:string;quote:string}>;reason?:string;usage?:Record<string,unknown>}}
export interface RagVersion { dataset_version_id: string; dataset_id: string; version: string; product_type: string }
export interface RagIndex { index_version_id: string; dataset_version_id: string; status: string; chunk_count: number; error_code: string | null; config: Record<string, unknown> }
export interface RagHit { chunk_id: string; segment_id: string; source_id: string; asset_id: string; document_version_id: string; text: string; rank: number; location: Record<string, unknown>; scores: Record<string, number | null> }
export interface RagTrace { trace_id: string; query: string; status: string; hits: RagHit[]; elapsed_ms: number; redacted_hit_count: number; generation: {status: string; answer: string | null} }
export interface RagSuite { suite_id: string; name: string; case_count: number; sha256: string; annotation_note: string }
export interface RagEvaluation { evaluation_id: string; status: string; error_code: string | null; report?: { suite_sha256?: string; metrics?: Record<string, unknown>; cases?: Array<{case_id: string; trace_id: string; metrics: Record<string, number | null>}> } }
export interface RagFeedback { feedback_id: string; quality_issue_id: string; segment_id: string; status: string; note: string; category: string; run_id: string }
const post = (body: unknown) => ({method: 'POST', body: JSON.stringify(body)});
export const ragApi = {
 generate: (ctx:ApiContext,trace_id:string)=>request<GeneratedAnswer>('/rag/answers',ctx,post({trace_id,request_key:crypto.randomUUID()})),
 answer: (ctx:ApiContext,id:string)=>request<GeneratedAnswer>(`/rag/answers/${id}`,ctx),
 review: (ctx: ApiContext, body: unknown) => request<{review_id:string}>('/rag/reviews',ctx,post(body)),
 reviews: (ctx: ApiContext, id: string) => request<{reviewer_count:number;disagreement:number|null;items:unknown[];scope:string}>(`/rag/traces/${id}/reviews`,ctx),
 versions: (ctx: ApiContext) => request<{items: RagVersion[]}>('/rag/versions',ctx),
 indexes: (ctx: ApiContext) => request<{items: RagIndex[]}>('/rag/indexes',ctx),
 build: (ctx: ApiContext, id: string, embedding = false) => request<RagIndex>('/rag/indexes',ctx,post({dataset_version_id:id,embedding,request_key:crypto.randomUUID()})),
 query: (ctx: ApiContext, body: unknown) => request<RagTrace>('/rag/queries',ctx,post(body)),
 trace: (ctx: ApiContext, id: string) => request<RagTrace>(`/rag/traces/${id}`,ctx),
 suites: (ctx: ApiContext) => request<{items: RagSuite[]}>('/rag/suites',ctx),
 createSuite: (ctx: ApiContext, id: string, note: string) => request<{suite_id:string}>('/rag/suites',ctx,post({dataset_version_id:id,name:'Web 核对评测集',annotation_note:note})),
 evaluate: (ctx: ApiContext, body: unknown) => request<RagEvaluation>('/rag/evaluations',ctx,post(body)),
 evaluations: (ctx: ApiContext) => request<{items:RagEvaluation[]}>('/rag/evaluations',ctx),
 evaluation: (ctx: ApiContext, id: string) => request<RagEvaluation>(`/rag/evaluations/${id}`,ctx),
 feedback: (ctx: ApiContext) => request<{items: RagFeedback[]}>('/rag/feedback',ctx),
 createFeedback: (ctx: ApiContext, body: unknown) => request<Pick<RagFeedback, 'feedback_id' | 'quality_issue_id' | 'run_id' | 'status'>>('/rag/feedback',ctx,post(body)),
};
