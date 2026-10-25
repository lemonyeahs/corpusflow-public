import {useEffect,useState} from 'react';
import {api,ApiError,type ApiContext} from '../api/client';
import {collectionApi,type Candidate,type IngestPlan} from '../api/collection';
import type {Source} from '../types';
import {Badge,Card,Empty,ErrorBox,Field,Loading,Page} from '../components';

export function CollectionPage({ctx}:{ctx:ApiContext}){
 const [candidates,setCandidates]=useState<Candidate[]>([]),[plans,setPlans]=useState<IngestPlan[]>([]),[sources,setSources]=useState<Source[]>([]);
 const [selected,setSelected]=useState<string[]>([]),[source,setSource]=useState(''),[url,setUrl]=useState(''),[title,setTitle]=useState(''),[doi,setDoi]=useState(''),[note,setNote]=useState('');
 const [metadata,setMetadata]=useState<unknown>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 function fail(e:unknown){setError(e instanceof ApiError?`${e.code}：${e.message}`:String(e));}
 async function load(){try{const [c,p,s]=await Promise.all([collectionApi.candidates(ctx),collectionApi.plans(ctx),api.sources(ctx)]);setCandidates(c.items);setPlans(p.items);setSources(s.items);}catch(e){fail(e);}}
 useEffect(()=>{void load();const timer=setInterval(()=>void load(),3000);return()=>clearInterval(timer);},[ctx.workspaceId]);
 async function act(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();await load();}catch(e){fail(e);}finally{setBusy(false);}}
 return <Page title="受控数据采集" subtitle="候选 → 独立审核采集计划 → 异步登记资产。采集许可不等于训练、RAG 或评测用途授权。">
 <div className="collection-content">{error&&<ErrorBox message={error}/>} {busy&&<Loading/>}
 <Card title="发现候选"><Field label="候选标题"><input aria-label="候选标题" value={title} onChange={e=>setTitle(e.target.value)}/></Field><Field label="HTTPS URL"><input aria-label="HTTPS URL" value={url} onChange={e=>setUrl(e.target.value)}/></Field><button className="button" disabled={busy||!title||!url} onClick={()=>void act(async()=>{await collectionApi.candidate(ctx,title,url);})}>登记候选</button><p>登记候选不访问网络。建立计划及执行时检查管理员域名白名单，公网 DNS、TLS、大小和超时；重定向直接拒绝。</p><Field label="DOI"><input aria-label="DOI" value={doi} onChange={e=>setDoi(e.target.value)}/></Field><button className="button secondary" disabled={busy||!doi} onClick={()=>void act(async()=>setMetadata(await collectionApi.doi(ctx,doi)))}>查询真实 DOI 元数据</button>{metadata!==null&&<pre>{JSON.stringify(metadata,null,2)}</pre>}</Card>
 <Card title="批量计划"><Field label="采集来源"><select aria-label="采集来源" value={source} onChange={e=>setSource(e.target.value)}><option value="">选择已登记来源</option>{sources.map(s=><option key={s.source_id} value={s.source_id}>{s.name}</option>)}</select></Field>{!candidates.length&&<Empty>尚无候选，不代表已接入资料。</Empty>}{candidates.map(c=><label key={c.candidate_id} className="list-row"><input type="checkbox" checked={selected.includes(c.candidate_id)} onChange={e=>setSelected(old=>e.target.checked?[...old,c.candidate_id]:old.filter(id=>id!==c.candidate_id))}/>{c.title} · {c.url}</label>)}<button className="button" disabled={busy||!source||!selected.length||selected.length>10} onClick={()=>void act(async()=>{await collectionApi.plan(ctx,source,selected);})}>建立待审核计划</button></Card>
 <Card title="采集审核与执行"><Field label="许可与采集依据"><textarea aria-label="许可与采集依据" value={note} onChange={e=>setNote(e.target.value)}/></Field><p>不同身份的审核员确认来源许可后才能排队；所有用途授权仍默认未授予。</p>{plans.map(p=><article className="issue-card" key={p.plan_id}><Badge value={p.status}/><p>{p.plan_id} · {p.error_code}</p><pre>{JSON.stringify(p,null,2)}</pre>{p.status==='draft'&&<><button className="button" disabled={busy||note.length<12} onClick={()=>void act(async()=>{await collectionApi.review(ctx,p.plan_id,true,note);})}>审核并异步采集</button><button className="button secondary" disabled={busy||note.length<12} onClick={()=>void act(async()=>{await collectionApi.review(ctx,p.plan_id,false,note);})}>驳回采集</button></>}</article>)}</Card>
 </div></Page>;
}
