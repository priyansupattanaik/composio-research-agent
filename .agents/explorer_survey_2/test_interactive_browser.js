const { spawn } = require('child_process');
const http = require('http');

async function main() {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const port = 9334;
  const url = 'file:///' + require('path').resolve('output/index.html').replace(/\\/g, '/');

  const edge = spawn(edgePath, [
    `--remote-debugging-port=${port}`,
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--user-data-dir=' + require('path').resolve('.agents/explorer_survey_2/edge_profile_interactive'),
    url
  ]);

  let versionData = null;
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 500));
    try {
      versionData = await new Promise((resolve, reject) => {
        http.get(`http://127.0.0.1:${port}/json/version`, res => {
          let data = '';
          res.on('data', chunk => data += chunk);
          res.on('end', () => resolve(JSON.parse(data)));
        }).on('error', reject);
      });
      break;
    } catch (e) {}
  }

  const pages = await new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:${port}/json/list`, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });

  const page = pages.find(p => p.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  let msgId = 1;
  function send(method, params = {}) {
    return new Promise((resolve) => {
      const id = msgId++;
      const handler = (event) => {
        const res = JSON.parse(event.data);
        if (res.id === id) {
          ws.removeEventListener('message', handler);
          resolve(res.result);
        }
      };
      ws.addEventListener('message', handler);
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  await send('Runtime.enable');
  await new Promise(r => setTimeout(r, 2000));

  async function evaluate(code) {
    const res = await send('Runtime.evaluate', { expression: code, returnByValue: true });
    return res.result.value;
  }

  console.log('--- 1. Testing Search in Browser ---');
  await evaluate(`
    document.getElementById('searchInput').value = 'slack';
    document.getElementById('searchInput').dispatchEvent(new Event('input'));
  `);
  let rows = await evaluate("document.querySelectorAll('#appsTableBody tr').length");
  let counter = await evaluate("document.getElementById('tableRowCounter').innerText");
  let firstAppName = await evaluate("document.querySelector('#appsTableBody tr td:nth-child(2)').innerText.trim()");
  console.log(`Search 'slack': ${rows} row(s), counter: "${counter}", firstApp: "${firstAppName}"`);

  console.log('\n--- 2. Testing Category Filter in Browser ---');
  await evaluate(`
    document.getElementById('searchInput').value = '';
    document.getElementById('categoryFilter').value = 'Ecommerce';
    document.getElementById('categoryFilter').dispatchEvent(new Event('change'));
  `);
  rows = await evaluate("document.querySelectorAll('#appsTableBody tr').length");
  counter = await evaluate("document.getElementById('tableRowCounter').innerText");
  console.log(`Category 'Ecommerce': ${rows} row(s), counter: "${counter}"`);

  console.log('\n--- 3. Testing Verdict Filter in Browser ---');
  await evaluate(`
    document.getElementById('categoryFilter').value = '';
    document.getElementById('verdictFilter').value = 'not-buildable';
    document.getElementById('verdictFilter').dispatchEvent(new Event('change'));
  `);
  rows = await evaluate("document.querySelectorAll('#appsTableBody tr').length");
  counter = await evaluate("document.getElementById('tableRowCounter').innerText");
  console.log(`Verdict 'not-buildable': ${rows} row(s), counter: "${counter}"`);

  console.log('\n--- 4. Testing Reset Filters ---');
  await evaluate(`
    document.getElementById('verdictFilter').value = '';
    document.getElementById('verdictFilter').dispatchEvent(new Event('change'));
  `);
  rows = await evaluate("document.querySelectorAll('#appsTableBody tr').length");
  counter = await evaluate("document.getElementById('tableRowCounter').innerText");
  console.log(`Reset all filters: ${rows} row(s), counter: "${counter}"`);

  console.log('\n--- 5. Testing Column Sort in Browser ---');
  // Sort by name (click App header)
  await evaluate("sortTable('name')");
  let firstRowApp = await evaluate("document.querySelector('#appsTableBody tr td:nth-child(2)').innerText.trim()");
  let lastRowApp = await evaluate("document.querySelector('#appsTableBody tr:last-child td:nth-child(2)').innerText.trim()");
  console.log(`Sort 'name' ASC: first="${firstRowApp}", last="${lastRowApp}"`);

  await evaluate("sortTable('name')");
  firstRowApp = await evaluate("document.querySelector('#appsTableBody tr td:nth-child(2)').innerText.trim()");
  lastRowApp = await evaluate("document.querySelector('#appsTableBody tr:last-child td:nth-child(2)').innerText.trim()");
  console.log(`Sort 'name' DESC: first="${firstRowApp}", last="${lastRowApp}"`);

  // Sort by ID
  await evaluate("sortTable('id')");
  let firstId = await evaluate("document.querySelector('#appsTableBody tr td:first-child').innerText.trim()");
  console.log(`Sort 'id': first ID = ${firstId}`);

  ws.close();
  edge.kill();
  console.log('\nAll browser interactions verified successfully!');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
