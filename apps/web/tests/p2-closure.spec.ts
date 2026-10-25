import {expect,test} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

test('P2-Closure Docker layout text and immutable located output',async({page})=>{
 const root=path.resolve(process.cwd(),'../..');
 execFileSync(path.join(root,'.venv/bin/python'),['scripts/verify_closure_layout.py'],{cwd:root,timeout:90_000});
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'.local/closure/layout-web.json'),'utf8'));
 await page.goto('/');
 await page.evaluate(s=>localStorage.setItem('corpusflow.p0h.session',JSON.stringify(s)),fixture.session);
 await page.reload();
 await page.getByRole('button',{name:'资产中心',exact:true}).click();
 await page.getByRole('button',{name:'columns.pdf',exact:true}).click();
 await expect(page.getByText('LEFT-ONE AES',{exact:false}).first()).toBeVisible();
 await expect(page.getByText('local.poppler-layout',{exact:false}).first()).toBeVisible();
 await page.screenshot({path:path.join(root,'.local/closure/layout-web.png'),fullPage:true});
});

test('P2-Closure assigned blind scoring and real agreement export',async({page})=>{
 const root=path.resolve(process.cwd(),'../..');
 execFileSync(path.join(root,'.venv/bin/python'),['scripts/verify_closure_reviews.py'],{cwd:root,timeout:60_000});
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'.local/closure/review-web.json'),'utf8'));
 await page.goto('/');
 await page.evaluate(s=>localStorage.setItem('corpusflow.p0h.session',JSON.stringify(s)),fixture.session);
 await page.reload();
 await page.getByRole('button',{name:'盲评任务',exact:true}).click();
 await page.getByRole('button',{name:fixture.assignment_id,exact:true}).click();
 await expect(page.getByTestId('blind-answer').first()).toContainText('128');
 await expect(page.getByRole('button',{name:'查看汇总',exact:true})).toHaveCount(0);
 for(const i of [1,2]){
  for(const field of ['evidence_support','completeness','answer_correctness'])await page.getByLabel(`${i} ${field}`,{exact:true}).selectOption('4');
  await page.getByLabel(`${i} 评分理由`,{exact:true}).fill('Original AES evidence fixture. Synthetic workflow score, NOT expert judgment.');
 }
 await page.getByRole('button',{name:'提交独立评分',exact:true}).click();
 await expect(page.getByRole('button',{name:'已提交，不可覆盖',exact:true})).toBeDisabled();
 await expect(page.getByLabel('1 evidence_support',{exact:true})).toHaveValue('4');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:path.join(root,'.local/closure/blind-review.png'),fullPage:true,animations:'disabled'});
 await page.evaluate(s=>localStorage.setItem('corpusflow.p0h.session',JSON.stringify(s)),fixture.admin);
 await page.reload();
 await page.getByRole('button',{name:'打开菜单',exact:true}).click();
 await page.getByRole('button',{name:'盲评任务',exact:true}).click();
 await page.getByLabel('评测任务 ID',{exact:true}).fill(fixture.task_id);
 await page.getByRole('button',{name:'查看汇总',exact:true}).click();
 await expect(page.getByTestId('blind-report')).toContainText('quadratic_weighted_kappa');
 const downloaded=page.waitForEvent('download');
 await page.getByRole('button',{name:'下载标注 JSON',exact:true}).click();
 const download=await downloaded;await download.saveAs(path.join(root,'.local/closure/review-export.json'));
 const report=JSON.parse(fs.readFileSync(path.join(root,'.local/closure/review-export.json'),'utf8'));
 expect(report.complete_reviewers).toBe(2);
 expect(report.snapshot_sha256).toBe(fixture.snapshot_sha256);
 expect(report.pairwise_agreement[0].dimensions.evidence_support.exact_agreement).toBe(0);
});
