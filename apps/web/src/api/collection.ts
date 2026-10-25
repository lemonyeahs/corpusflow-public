import {request,type ApiContext} from './client';
export interface Candidate {candidate_id:string;title:string;url:string;state:string}
export interface IngestPlan {plan_id:string;status:string;config:Record<string,unknown>;results:unknown[];review_note:string;error_code:string|null}
const post=(body:unknown)=>({method:'POST',body:JSON.stringify(body)});
export const collectionApi={
 candidates:(ctx:ApiContext)=>request<{items:Candidate[]}>('/collection/candidates',ctx),
 candidate:(ctx:ApiContext,title:string,url:string)=>request<Candidate>('/discovery-candidates',ctx,post({title,url})),
 plans:(ctx:ApiContext)=>request<{items:IngestPlan[]}>('/collection/plans',ctx),
 plan:(ctx:ApiContext,source_id:string,candidate_ids:string[])=>request<IngestPlan>('/collection/plans',ctx,post({source_id,candidate_ids,request_key:crypto.randomUUID()})),
 review:(ctx:ApiContext,id:string,approve:boolean,legal_basis:string)=>request<IngestPlan>(`/collection/plans/${id}/review`,ctx,post({approve,legal_basis})),
 doi:(ctx:ApiContext,doi:string)=>request<Record<string,unknown>>('/collection/doi-metadata',ctx,post({doi})),
};
