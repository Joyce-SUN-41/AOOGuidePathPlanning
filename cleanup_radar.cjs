const fs = require('fs');
let f = fs.readFileSync('e:/AOOGuidePathPlanning/src/views/PathView.vue', 'utf8');

// Pattern of the injected radar CSS block
const radarBlockRegex = /\/\/ {3}三路径雷达图\n\/\/ ============================================================\n\.radar-section \{[\s\S]*?max-height: 420px;\n\}/g;

let cleaned = f.replace(radarBlockRegex, '');

// Clean standalone '三路径雷达图' headers
cleaned = cleaned.replace(/\n\/\/\s{3}三路径雷达图\n\/\/ ============================================================\n/g, '\n');

fs.writeFileSync('e:/AOOGuidePathPlanning/src/views/PathView.vue', cleaned, 'utf8');
let count = (cleaned.match(/\.radar-section\s*\{/g)||[]).length;
console.log('radar-section count after cleanup:', count);
console.log('Total lines:', cleaned.split('\n').length);
