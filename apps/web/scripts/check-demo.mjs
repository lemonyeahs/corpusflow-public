import { createServer } from 'vite';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const server = await createServer({ root, mode: 'demo', cacheDir: fileURLToPath(new URL('../../../.local/frontend-demo/test-vite', import.meta.url)), optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true, hmr: false }, appType: 'custom' });
let network = 0;
const realFetch = globalThis.fetch;
globalThis.fetch = () => { network++; throw new Error('Unexpected backend request'); };
try {
  const { request, api } = await server.ssrLoadModule('/src/api/client.ts');
  const { download } = await server.ssrLoadModule('/src/api/download.ts');
  const { demoSession } = await server.ssrLoadModule('/src/app/demo-mode.ts');
  const context = { token: demoSession.token, workspaceId: demoSession.workspace_id };
  const get = path => request(path, context);
  assert.equal((await get('/auth/me')).user_id, demoSession.user_id);
  const overview = await get('/training-center/overview?catalog=workspace');
  assert.equal(overview.metrics.training_record_count.value, 300000);
  assert.equal(overview.formats.reduce((s, f) => s + f.file_count, 0), 1200);
  for (const d of overview.datasets) {
    assert.equal(Object.values(d.split_counts).reduce((a,b) => a+b), d.record_count);
    const base = `/training-center/datasets/${d.id}/samples?catalog=workspace&version=${d.version}`;
    const first = await get(base);
    const last = await get(`${base}&offset=${d.record_count-20}`);
    assert.equal(first.items.length, 20);
    assert.equal(last.items.at(-1).sequence, d.record_count);
    assert.equal(last.total_count, d.record_count);
    assert.equal((await get(`${base}&offset=${d.record_count}`)).items.length, 0);
    assert.equal((await get(`${base}&split=test`)).total_count, d.split_counts.test);
    assert.equal((await get(`${base}&q=not-found-xyz`)).total_count, 0);
  }
  const files = await get('/training-center/files?catalog=workspace&format=pdf');
  const stats = await get('/training-center/formats/pdf/stats?catalog=workspace');
  assert.equal(files.total_count, 240);
  assert.equal(stats.metrics.file_count.value, files.total_count);
  assert.equal(stats.ingestion_trend.points.reduce((s,p) => s+p.count,0), files.total_count);
  const comparison = await get(`/training-center/files/${files.items[0].id}/comparison?catalog=workspace`);
  assert.equal(comparison.before.record_id, comparison.after.record_id);
  assert.notEqual(comparison.before.text, comparison.after.text);
  assert.match(comparison.after.text, /\[EMAIL\]/);
  await assert.rejects(get('/unsupported'), /纯前端/);
  await assert.rejects(request('/sources',context,{method:'POST',body:'{}'}), /纯前端/);
  await assert.rejects(download('/exports',context,'demo.jsonl'), /纯前端/);
  await assert.rejects(api.uploadContent(context,'upload',new Blob(['test'])), /纯前端/);
  assert.equal(network, 0);
  console.log('Frontend demo: counts, pagination, filters, comparisons and zero backend I/O passed.');
} finally {
  globalThis.fetch = realFetch;
  await server.close();
}
