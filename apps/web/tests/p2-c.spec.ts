import {expect,test} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

test('P2-C Docker OCR and fail-closed acquisition are visible',async({page})=>{
 test.setTimeout(180_000);
 const root=path.resolve(process.cwd(),'../..');
 for(const script of ['scripts/verify_p2_ocr.py','scripts/verify_p2_collection.py'])execFileSync(path.join(root,'.venv/bin/python'),[script],{cwd:root,timeout:90_000});
 const ocr=JSON.parse(fs.readFileSync(path.join(root,'.local/p2/ocr-web.json'),'utf8'));
 await page.goto('/');
 await page.evaluate(s=>localStorage.setItem('corpusflow.p0h.session',JSON.stringify(s)),ocr.session);
 await page.reload();
 await page.getByRole('button',{name:'资产中心',exact:true}).click();
 await page.getByRole('button',{name:'raster.pdf',exact:true}).click();
 await expect(page.getByText('CorpusFlow OCR evidence:',{exact:false}).first()).toBeVisible();
 const collection=JSON.parse(fs.readFileSync(path.join(root,'.local/p2/collection-web.json'),'utf8'));
 await page.evaluate(s=>localStorage.setItem('corpusflow.p0h.session',JSON.stringify(s)),collection.session);
 await page.reload();
 await page.getByRole('button',{name:'受控采集',exact:true}).click();
 await expect(page.getByText('ACQUISITION_ADDRESS_REJECTED',{exact:false}).first()).toBeVisible();
 await page.getByLabel('候选标题',{exact:true}).fill('Local disallowed target');
 await page.getByLabel('HTTPS URL',{exact:true}).fill('https://127.0.0.1/private');
 await page.getByRole('button',{name:'登记候选',exact:true}).click();
 await expect(page.getByText('Local disallowed target',{exact:false}).first()).toBeVisible();
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
