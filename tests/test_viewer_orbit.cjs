const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('viewer/splat-viewer.js', 'utf8').split('function createWorker(self)')[0];
vm.runInThisContext(source + `
// Offset model and translated/rotated camera: the former fixed-distance pivot fails here.
orbitCenter = [2, -1, 5];
let m = translate4(rotate4([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1], .35, 0,1,0), -3,2,-4);
const transform = m => {const v=invert4(m); return orbitCenter.map((_,r)=>v[r]*orbitCenter[0]+v[4+r]*orbitCenter[1]+v[8+r]*orbitCenter[2]+v[12+r]);};
globalThis.orbitTest = { before:transform(m), after:transform(orbitAroundCenter(m,.7,-.4)),
 radiusBefore: Math.hypot(...orbitCenter.map((x,i)=>x-m[12+i])),
 radiusAfter: Math.hypot(...orbitCenter.map((x,i)=>x-orbitAroundCenter(m,.7,-.4)[12+i])) };
`);
for(let i=0;i<3;i++) assert.ok(Math.abs(orbitTest.before[i]-orbitTest.after[i])<1e-10);
assert.ok(Math.abs(orbitTest.radiusBefore-orbitTest.radiusAfter)<1e-10);
console.log('Orbit pivot projection and radius remain fixed.');
