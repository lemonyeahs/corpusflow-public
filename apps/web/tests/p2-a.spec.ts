import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

test('P2-A real persisted semantic index and query', async ({page}) => {
 test.setTimeout(240_000);
 const root = path.resolve(process.cwd(), '../..');
 execFileSync(path.join(root,'.venv/bin/python'), ['scripts/verify_p2_semantic.py'], {cwd:root,timeout:180_000});
 const fixture = JSON.parse(fs.readFileSync(path.join(root,'.local/p1d/web.json'),'utf8'));
 const state = JSON.parse(fs.readFileSync(path.join(root,'.local/p2/semantic-web.json'),'utf8'));
 await page.goto('/');
 await page.evaluate(s=>localStorage.setItem('corpusflow.p0h.session',JSON.stringify(s)),fixture.session);
 await page.reload();
 await page.getByRole('button',{name:'下游验证',exact:true}).click();
 await page.getByLabel('检索索引',{exact:true}).selectOption(state.index_id);
 await page.getByLabel('检索策略',{exact:true}).selectOption('vector');
 await page.getByLabel('查询',{exact:true}).fill('AES block size');
 await page.getByRole('button',{name:'执行真实查询',exact:true}).click();
 await expect(page.getByTestId('rag-result-status')).toContainText('EVIDENCE_FOUND');
 await expect(page.getByText('AES is a symmetric block cipher.',{exact:false}).first()).toBeVisible();
 await expect(page.getByText('"cosine":',{exact:false}).first()).toBeVisible();
 await page.getByLabel('余弦阈值',{exact:true}).fill('1');
 await page.getByRole('button',{name:'执行真实查询',exact:true}).click();
 await expect(page.getByTestId('rag-result-status')).toContainText('NO_EVIDENCE');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
