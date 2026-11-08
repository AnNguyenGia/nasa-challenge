import test from 'node:test';
import assert from 'node:assert/strict';
import {deliver,retryDelay} from '../src/delivery.js';
const row = {id:'one',reading:{id:'one'},state:'pending',attempts:0};
test('outage retains record and schedules retry',async()=>{
 const result=await deliver(row,async()=>{throw Error('network')},1000);
 assert.equal(result.state,'pending');assert.equal(result.reading,row.reading);assert.ok(result.retryAt>1000);
});
test('lost ACK replay preserves same ID and accepts dedup acknowledgment',async()=>{
 let committed;
 const outage=await deliver(row,async(_m,_p,body)=>{committed=body.id;throw Error('lost ACK')});
 const recovered=await deliver(outage,async(_m,_p,body)=>({ok:true,data:{id:committed,duplicate:body.id===committed}}));
 assert.equal(recovered.state,'sent');assert.equal(recovered.id,row.id);
});
test('409 is retained for operator review',async()=>assert.equal((await deliver(row,async()=>({ok:false,status:409}))).state,'blocked'));
test('invalid acknowledgment must not drop data',async()=>assert.equal((await deliver(row,async()=>({ok:true,data:{id:'other'}}))).state,'pending'));
test('backoff is capped',()=>assert.equal(retryDelay(100,()=>0),60000));
