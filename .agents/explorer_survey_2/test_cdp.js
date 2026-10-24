const { spawn } = require('child_process');
const http = require('http');

async function main() {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const port = 9333;
  const url = 'file:///' + require('path').resolve('output/index.html').replace(/\\/g, '/');

  console.log('Target URL:', url);

  const edge = spawn(edgePath, [
    `--remote-debugging-port=${port}`,
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--user-data-dir=' + require('path').resolve('.agents/explorer_survey_2/edge_profile'),
    url
  ]);

  // Wait for DevTools endpoint
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

  if (!versionData) {
    console.error('Failed to connect to Edge debugging port');
    edge.kill();
    return;
  }

  console.log('Connected to Edge:', versionData.Browser);

  // Get pages
  const pages = await new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:${port}/json/list`, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });

  const page = pages.find(p => p.type === 'page');
  if (!page || !page.webSocketDebuggerUrl) {
    console.error('No page found');
    edge.kill();
    return;
  }

  // Connect WebSocket to page
  const ws = new WebSocket(page.webSocketDebuggerUrl);

  const consoleMessages = [];
  const networkErrors = [];

  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });

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

  ws.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    if (data.method === 'Console.messageAdded') {
      consoleMessages.push(data.params.message);
    }
    if (data.method === 'Runtime.consoleAPICalled') {
      consoleMessages.push(data.params);
    }
    if (data.method === 'Network.loadingFailed') {
      networkErrors.push(data.params);
    }
    if (data.method === 'Network.responseReceived') {
      if (data.params.response.status >= 400) {
        networkErrors.push(data.params);
      }
    }
  });

  await send('Console.enable');
  await send('Network.enable');
  await send('Runtime.enable');
  await send('Page.enable');

  // Reload page to capture all initial logs and network requests
  await send('Page.reload');

  // Wait 3 seconds for rendering & network
  await new Promise(r => setTimeout(r, 3000));

  // Evaluate expressions in page context
  const evalTableRows = await send('Runtime.evaluate', {
    expression: "document.querySelectorAll('#appsTableBody tr').length"
  });
  const evalVerifiedRows = await send('Runtime.evaluate', {
    expression: "document.querySelectorAll('#verifiedTableBody tr').length"
  });
  const evalChart1 = await send('Runtime.evaluate', {
    expression: "typeof Chart !== 'undefined' && Chart.getChart('authDonutChart') ? 'rendered' : 'missing'"
  });
  const evalChart2 = await send('Runtime.evaluate', {
    expression: "typeof Chart !== 'undefined' && Chart.getChart('buildabilityBarChart') ? 'rendered' : 'missing'"
  });
  const evalChart3 = await send('Runtime.evaluate', {
    expression: "typeof Chart !== 'undefined' && Chart.getChart('accessCategoryChart') ? 'rendered' : 'missing'"
  });
  const evalChart4 = await send('Runtime.evaluate', {
    expression: "typeof Chart !== 'undefined' && Chart.getChart('selfServeRateChart') ? 'rendered' : 'missing'"
  });

  console.log('Main table rows in browser:', evalTableRows.result.value);
  console.log('Verified table rows in browser:', evalVerifiedRows.result.value);
  console.log('Chart 1 authDonutChart:', evalChart1.result.value);
  console.log('Chart 2 buildabilityBarChart:', evalChart2.result.value);
  console.log('Chart 3 accessCategoryChart:', evalChart3.result.value);
  console.log('Chart 4 selfServeRateChart:', evalChart4.result.value);

  console.log('\n--- Browser Console Messages ---');
  console.log('Total console messages:', consoleMessages.length);
  consoleMessages.forEach(m => console.log(JSON.stringify(m)));

  console.log('\n--- Browser Network Errors ---');
  console.log('Total network errors:', networkErrors.length);
  networkErrors.forEach(e => console.log(JSON.stringify(e)));

  ws.close();
  edge.kill();
  console.log('\nCDP verification test complete.');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
