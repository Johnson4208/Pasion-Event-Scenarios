/** Exercise the admin page through Vite and the actual Python API, both on disposable ports. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {mkdtemp, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {chromium} from '@playwright/test';
import {createServer} from 'vite';

const root = fileURLToPath(new URL('../', import.meta.url));
const temp = await mkdtemp(path.join(tmpdir(), 'pasion-lab-ui-'));
const email = 'lab-admin@example.test';
const password = randomBytes(24).toString('hex');
const bootstrap = `
import os, sys
from pathlib import Path
sys.path.insert(0, 'backend')
import server
server.ROOT = Path(sys.argv[1])
with server.ExclusiveHTTPServer(('127.0.0.1', 0), server.Handler) as http:
    print(http.server_port, flush=True)
    http.serve_forever()
`;
const api = spawn(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),
  ['-u','-c',bootstrap,temp], {cwd:root,stdio:['ignore','pipe','inherit'],
    env:{...process.env,PASION_ENV:'test',PASION_ADMIN_EMAIL:email,SOLVAI_EMAIL:email,SOLVAI_PASSWORD:password,
      TMPDIR:temp,TEMP:temp,TMP:temp}});
const lines = createInterface({input:api.stdout});
const ended = new Promise(resolve=>api.once('close',resolve));
let vite, browser;
try {
  const port = await new Promise((resolve,reject)=>{
    api.once('error',reject);
    api.once('exit',()=>reject(new Error('Disposable API stopped.')));
    lines.once('line',line=>Number(line)>0 ? resolve(Number(line)) : reject(new Error('Invalid API port.')));
  });
  vite = await createServer({root,logLevel:'error',server:{host:'127.0.0.1',port:0,
    proxy:{'/api':'http://127.0.0.1:'+port}}});
  await vite.listen();
  const url='http://127.0.0.1:'+vite.httpServer.address().port;
  browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined});
  const page=await browser.newPage({viewport:{width:1365,height:960}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const login=await page.request.post(url+'/api/login',{data:{email,password}});
  assert.equal(login.status(),200);
  assert.equal((await login.json()).isAdmin,true);
  const button=name=>page.getByRole('button',{name,exact:true});
  const open=async()=>{await page.goto(url+'/#admin');await button('Trading & Distribution Monitor').click();};
  const state=async()=>(await (await page.request.get(url+'/api/admin/distribution/lab')).json()).run;
  async function create(horizon) {
    await button(horizon).click();
    await page.getByText('Thông số thuật toán và tốc độ',{exact:true}).click();
    await page.locator('[name=speed]').fill(horizon==='1 năm'?'12':'60');
    await button('Tạo lượt mô phỏng').click();
    await button('Tiến 1 ngày').waitFor();
  }
  async function finish() {
    await button('Chạy mô phỏng').click();
    await page.getByText('Hoàn tất',{exact:true}).waitFor({timeout:90000});
    return state();
  }
  await open();
  await button('Ngẫu nhiên').click();
  await create('1 năm');
  await button('Tiến 1 ngày').click();
  await page.getByRole('heading',{name:'Ngày 1 / 365'}).waitFor();
  await button('Chạy mô phỏng').click();
  await page.waitForFunction(()=>document.querySelector('.dl-clock progress')?.value>3);
  await page.getByLabel('Thêm khách giả lập').fill('125');
  await button('Thêm khách').click();
  await page.locator('.dl-kpis').getByText('225',{exact:true}).waitFor();
  await button('Tạm dừng').click();
  await button('Tiến 1 ngày').waitFor();
  const paused=await state();
  assert.equal(paused.status,'paused');
  await page.getByText('Chỉnh giới hạn và tốc độ',{exact:true}).click();
  await page.locator('[name=max_per_symbol]').fill('2');
  await page.locator('[name=speed]').fill('60');
  const saved=page.waitForResponse(r=>r.url().endsWith('/lab') && r.request().method()==='POST');
  await button('Áp dụng thông số').click();
  assert.equal((await saved).status(),200);
  await page.reload();
  await button('Trading & Distribution Monitor').click();
  assert.equal((await state()).day,paused.day);
  assert.equal((await state()).config.max_per_symbol,2);
  const one=await finish();
  assert.equal(one.day,365);
  assert.equal(one.config.customers,225);
  assert.ok(one.totals.redirected>0 && one.totals.withheld>0);
  await button('Lượt mới').click();
  await create('2 năm');
  const two=await finish();
  assert.ok(two.paper.totals.buys>0 && two.paper.totals.sells>0);
  assert.equal(two.paper.totals.notional,two.history.reduce((sum,d)=>sum+d.paper.notional,0));
  await page.getByRole('heading',{name:'Sổ giao dịch mô phỏng'}).waitFor();
  assert.ok((await page.locator('.dl-paper').innerText()).includes(two.paper.top_accounts[0].customer));
  await button('Sổ tài khoản & Shadow').click();
  await page.getByRole('heading',{name:'Account activity'}).waitFor();
  await page.getByText('No eligible manual trade records',{exact:true}).waitFor();
  await button('Distribution Lab').click();
  await page.getByText('Hoàn tất',{exact:true}).waitFor();
  assert.equal((await state()).id,two.id);
  assert.equal(two.day,730);
  assert.equal(two.totals.selected+two.totals.withheld,two.totals.requests);
  const download=page.waitForEvent('download');
  await button('Xuất kết quả JSON').click();
  const contents=JSON.parse(await readFile(await (await download).path(),'utf8'));
  assert.equal(contents.run.history.length,730);
  assert.deepEqual(contents.run.totals,two.totals);
  await page.setViewportSize({width:390,height:844});
  const widths=await page.locator('.distribution-lab').evaluate(el=>[el.getBoundingClientRect().width,el.scrollWidth]);
  assert.ok(widths[1]<=widths[0]+1,JSON.stringify(widths));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({oneYear:one.totals,twoYears:two.totals,paper:two.paper.totals,exportDays:contents.run.history.length}));
} finally {
  await browser?.close();
  await vite?.close();
  api.kill();
  await ended;
  lines.close();
  await rm(temp,{recursive:true,force:true});
}
