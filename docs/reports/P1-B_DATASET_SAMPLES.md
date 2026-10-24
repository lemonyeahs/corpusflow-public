# CorpusFlow P1-B 数据集样例

日期：2026-10-24

以下内容直接读取自本地 MinIO 已发布对象；没有使用固定演示字符串。每类展示一个实际 JSONL 首行和对应 Manifest 摘要。

## pretrain

- dataset_id：`e3871d7c-c12b-4b1b-bcd6-e14a15415852`
- dataset_version_id：`de5c2424-d718-4cca-a8fd-56b0b68ee55f`
- version：`2.0.79496`
- build_id：`c5bc2e3d-0c8f-419a-bddd-3281415a6cdb`
- schema：`pretrain.v1`
- purpose：`training`
- sample_count：1
- content SHA-256：`669f8f815d6d86e31cc76491314e70a3d44f8000f7310ab7a10858465eb15157`
- bytes：393
- source/segment：`{'source_id': '038c3409-510f-4890-8ffe-d141471fe01f', 'document_version_id': '0f84ad12-d315-46a5-b782-8ffba1e94d53', 'segment_id': '524ad1bb-cff8-44b3-9b6f-28ae84c7a067'}`

```json
{"text":"gamma evidence","metadata":{"source_id":"038c3409-510f-4890-8ffe-d141471fe01f","segment_ids":["524ad1bb-cff8-44b3-9b6f-28ae84c7a067"],"product_type":"pretrain","tokenizer_version":"builtin-whitespace-1","sample_id":"5592c0c2-699d-41d8-a606-1de294eeaf90","evidence_ids":["524ad1bb-cff8-44b3-9b6f-28ae84c7a067"],"split":"train"},"evidence_ids":["524ad1bb-cff8-44b3-9b6f-28ae84c7a067"]}
```

## rag

- dataset_id：`73affd1b-f167-46fc-a8c6-412feee1a5de`
- dataset_version_id：`8549f80e-9d05-4c2a-9eb2-f31eb9c552f3`
- version：`2.0.6825`
- build_id：`86aca969-b69c-4095-9c0b-3f2942b9e788`
- schema：`rag.v1`
- purpose：`rag`
- sample_count：1
- content SHA-256：`3c0e4bb4da50c11d993c3b8a8baa5792fa6c287648ac9d81243a5dc0ddb1984d`
- bytes：600
- source/segment：`{'source_id': '038c3409-510f-4890-8ffe-d141471fe01f', 'document_version_id': '0f84ad12-d315-46a5-b782-8ffba1e94d53', 'segment_id': '524ad1bb-cff8-44b3-9b6f-28ae84c7a067'}`

```json
{"text":"gamma evidence","unit":"tokens","overlap":1,"location":{"line":1},"metadata":{"product_type":"rag","sample_id":"769dd872-8091-42f4-8291-b88de3e7f3c1","source_id":"038c3409-510f-4890-8ffe-d141471fe01f","evidence_ids":["524ad1bb-cff8-44b3-9b6f-28ae84c7a067"],"split":"all"},"source_id":"038c3409-510f-4890-8ffe-d141471fe01f","chunk_size":3,"segment_id":"524ad1bb-cff8-44b3-9b6f-28ae84c7a067","chunk_index":0,"evidence_ids":["524ad1bb-cff8-44b3-9b6f-28ae84c7a067"],"section_title":"gamma","tokenizer_version":"builtin-whitespace-1","document_version_id":"0f84ad12-d315-46a5-b782-8ffba1e94d53"}
```

## evaluation

- dataset_id：`f73c5372-8a12-4211-8d9c-ad60752c7a89`
- dataset_version_id：`773f12d7-709c-46ee-a1fa-0e9cc7edea61`
- version：`2.0.33421`
- build_id：`839788fd-2090-42da-b6b4-d29d7b5deda5`
- schema：`evaluation.v1`
- purpose：`evaluation`
- sample_count：1
- content SHA-256：`7a86cab00dee41d3b041f28018697978ce66f23f4d02a1e5542a1f40ad6485be`
- bytes：538
- source/segment：`{'source_id': '038c3409-510f-4890-8ffe-d141471fe01f', 'document_version_id': '0f84ad12-d315-46a5-b782-8ffba1e94d53', 'segment_id': '524ad1bb-cff8-44b3-9b6f-28ae84c7a067'}`

```json
{"domain":"technical","question":"What is the source segment about?","difficulty":"easy","source_ids":["038c3409-510f-4890-8ffe-d141471fe01f"],"evidence_ids":["524ad1bb-cff8-44b3-9b6f-28ae84c7a067"],"question_type":"open","review_status":"pending","quality_status":"pending","reference_answer":"The source segment contains the reviewed document text.","metadata":{"sample_id":"b8e940ec-60cf-4f16-acad-3443e5731ce8","source_id":"038c3409-510f-4890-8ffe-d141471fe01f","evidence_ids":["524ad1bb-cff8-44b3-9b6f-28ae84c7a067"],"split":"all"}}
```
