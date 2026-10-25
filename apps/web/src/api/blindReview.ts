import {request,type ApiContext} from './client';
export interface Assignment {assignment_id:string; submitted:boolean}
export interface BlindCase {case_number:number;query:string;answer:Record<string,unknown>|null;evidence:Array<{segment_id:string;text:string;location:Record<string,unknown>}>}
export interface BlindView extends Assignment {snapshot_sha256:string;rubric:Record<string,unknown>;cases:BlindCase[];own_scores:Score[]}
export interface Score {evidence_support?:number;completeness?:number;answer_correctness?:number;unsupported_answer?:boolean;irrelevant:boolean;no_answer_expected:boolean;note:string}
const post=(body:unknown)=>({method:'POST',body:JSON.stringify(body)});
export const blindApi={
 list:(ctx:ApiContext)=>request<{items:Assignment[]}>('/review-tasks/assignments',ctx),
 view:(ctx:ApiContext,id:string)=>request<BlindView>(`/review-tasks/assignments/${id}`,ctx),
 submit:(ctx:ApiContext,id:string,scores:Score[])=>request<{status:string}>(`/review-tasks/assignments/${id}/scores`,ctx,post({scores})),
 create:(ctx:ApiContext,cases:unknown[],reviewer_ids:string[])=>request<{task_id:string}>('/review-tasks',ctx,post({request_key:crypto.randomUUID(),cases,reviewer_ids})),
 export:(ctx:ApiContext,id:string)=>request<Record<string,unknown>>(`/review-tasks/${id}/export`,ctx),
};
