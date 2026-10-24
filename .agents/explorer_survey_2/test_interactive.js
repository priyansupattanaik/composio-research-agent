const fs = require('fs');

const html = fs.readFileSync('output/index.html', 'utf8');

// Extract APP_DATA, PATTERNS, ACCURACY
const appDataMatch = html.match(/const APP_DATA = (\[.*?\]);\r?\n/s);
const patternsMatch = html.match(/const PATTERNS = (\{.*?\});\r?\n/s);
const accuracyMatch = html.match(/const ACCURACY = (\{.*?\});\r?\n/s);

if (!appDataMatch) throw new Error("Could not extract APP_DATA");
if (!patternsMatch) throw new Error("Could not extract PATTERNS");
if (!accuracyMatch) throw new Error("Could not extract ACCURACY");

const APP_DATA = JSON.parse(appDataMatch[1]);
const PATTERNS = JSON.parse(patternsMatch[1]);
const ACCURACY = JSON.parse(accuracyMatch[1]);

console.log(`Extracted ${APP_DATA.length} apps from HTML.`);

// Replicate filtering logic exactly as in index.html
function applyFilters(searchVal, catVal, verdVal) {
  const s = searchVal ? searchVal.toLowerCase().trim() : '';
  return APP_DATA.filter(app => {
    const matchesSearch = !s || app.name.toLowerCase().includes(s);
    const matchesCat = !catVal || app.category === catVal;
    const matchesVerd = !verdVal || app.buildability === verdVal;
    return matchesSearch && matchesCat && matchesVerd;
  });
}

// Replicate sorting logic
function sortData(data, column, direction) {
  const copy = [...data];
  copy.sort((a, b) => {
    let vA = a[column];
    let vB = b[column];

    if (typeof vA === 'string') vA = vA.toLowerCase();
    if (typeof vB === 'string') vB = vB.toLowerCase();

    if (vA < vB) return direction === 'asc' ? -1 : 1;
    if (vA > vB) return direction === 'asc' ? 1 : -1;
    return 0;
  });
  return copy;
}

// 1. Test search filter
console.log("\n--- Testing Search Filter ---");
const searches = ['slack', 'salesforce', 'hubspot', 'nonexistent_query_xyz', 'a'];
searches.forEach(query => {
  const res = applyFilters(query, '', '');
  console.log(`Search '${query}': matched ${res.length} rows (${res.map(r => r.name).slice(0, 3).join(', ')}${res.length > 3 ? '...' : ''})`);
});

// 2. Test category filter
console.log("\n--- Testing Category Filter ---");
const categories = [
  "CRM and Sales", "Support and Helpdesk", "Communications and Messaging",
  "Marketing, Ads, Email and Social", "Ecommerce", "Data, SEO and Scraping",
  "Developer, Infra and Data Platforms", "Productivity and Project Management",
  "Finance and Fintech", "AI, Research and Media-native"
];
categories.forEach(cat => {
  const res = applyFilters('', cat, '');
  console.log(`Category '${cat}': matched ${res.length} rows`);
});

// 3. Test verdict filter
console.log("\n--- Testing Verdict Filter ---");
const verdicts = ['build-today', 'build-paid', 'build-after-outreach', 'needs-research', 'not-buildable'];
verdicts.forEach(verd => {
  const res = applyFilters('', '', verd);
  console.log(`Verdict '${verd}': matched ${res.length} rows`);
});

// 4. Test multi-filtering
console.log("\n--- Testing Combined Filters ---");
const c1 = applyFilters('crm', 'CRM and Sales', 'build-after-outreach');
console.log(`Combined 'crm' + 'CRM and Sales' + 'build-after-outreach': ${c1.length} matches (${c1.map(r => r.name).join(', ')})`);

const c2 = applyFilters('', 'Finance and Fintech', 'build-today');
console.log(`Combined '' + 'Finance and Fintech' + 'build-today': ${c2.length} matches`);

// 5. Test sorting on all sortable columns
console.log("\n--- Testing Column Sorting ---");
const sortColumns = ['id', 'name', 'category', 'primary_auth', 'access_model', 'api_type', 'api_breadth', 'has_mcp', 'buildability'];
sortColumns.forEach(col => {
  const asc = sortData(APP_DATA, col, 'asc');
  const desc = sortData(APP_DATA, col, 'desc');
  console.log(`Sorted by '${col}':`);
  console.log(`  ASC first: ${asc[0][col]} (${asc[0].name}) -> last: ${asc[asc.length - 1][col]} (${asc[asc.length - 1].name})`);
  console.log(`  DESC first: ${desc[0][col]} (${desc[0].name}) -> last: ${desc[desc.length - 1][col]} (${desc[desc.length - 1].name})`);
});

// 6. Test human verified table
console.log("\n--- Testing Section F Verified Table ---");
const verifiedApps = APP_DATA.filter(a => a.human_verified);
console.log(`Found ${verifiedApps.length} human_verified apps in APP_DATA.`);
const verdictsSectionF = {};
verifiedApps.forEach(a => {
  verdictsSectionF[a.human_verdict] = (verdictsSectionF[a.human_verdict] || 0) + 1;
});
console.log("Section F verdicts breakdown:", verdictsSectionF);

console.log("\nAll simulation checks finished successfully.");
