import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

test('P2-B evidence review workflow is real but does not invent expert scores',async({page})=>{
 const root=path.resolve(process.cwd(),'../..');
 execFileSync(path.join(root,'.venv/bin/python'),['scripts/verify_p2_reviews.py'],{cwd:root,timeout:60_000});
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'.local/p1d/web.json'),'utf8'));
 const state=JSON.parse(fs.readFileSync(path.join(root,'.local/p2/semantic-web.json'),'utf8'));
 await page.goto('/');
 await page.evaluate(s=>localStorage.setItem('corpusflow.p0h.session',JSON.stringify(s)),fixture.session);
 await page.reload();
 await page.getByRole('button',{name:'下游验证',exact:true}).click();
 await page.getByLabel('Trace ID',{exact:true}).fill(state.trace_id);
 await page.getByRole('button',{name:'查看历史查询',exact:true}).click();
 await page.getByLabel('核对依据 / 反馈说明',{exact:true}).fill('Web synthetic workflow check, not expert assessment');
 await page.getByLabel('证据支持性',{exact:true}).fill('2');
 await page.getByLabel('证据完整性',{exact:true}).fill('2');
 await page.getByRole('button',{name:'提交证据评分',exact:true}).click();
 await expect(page.getByTestId('review-report')).toContainText('"reviewer_count": 2');
 await page.reload();
 await page.getByRole('button',{name:'下游验证',exact:true}).click();
 await page.getByLabel('Trace ID',{exact:true}).fill(state.trace_id);
 await page.getByRole('button',{name:'查看历史查询',exact:true}).click();
 await page.getByRole('button',{name:'查看评分与分歧',exact:true}).click();
 await expect(page.getByTestId('review-report')).toContainText('NOT_VERIFIED');
});
