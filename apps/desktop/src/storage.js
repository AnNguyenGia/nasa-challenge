import { openDB } from 'idb';
import { deliver } from './delivery.js';
const database = openDB('space-health-v1', 1, {
  upgrade(db) { db.createObjectStore('outbox', {keyPath:'id'}); db.createObjectStore('cache'); }
});
export const entries = async () => (await database).getAll('outbox');
export async function enqueue(reading) {
  const db = await database;
  // add() prevents replacing a previously committed record with a colliding UUID.
  const tx = db.transaction('outbox', 'readwrite', {durability:'strict'});
  await Promise.all([tx.store.add({id:reading.id, reading, state:'pending', attempts:0, retryAt:0}), tx.done]);
}
export async function cache(key, value) {
  const db = await database;
  if (value !== undefined) await db.put('cache', value, key);
  return db.get('cache', key);
}
let syncing = false;
export async function sync(request) {
  if (syncing) return;
  syncing = true;
  try {
    const db = await database;
    const pending = (await entries()).filter(r => r.state === 'pending' && r.retryAt <= Date.now());
    for (const row of pending) {
      const result = await deliver(row, request);
      await db.put('outbox', result);
      if (result.state === 'pending') break;
    }
  } finally { syncing = false; }
}
