export function retryDelay(attempt, random = Math.random) {
  return Math.min(60000, 1000 * 2 ** Math.min(attempt, 6)) + random() * 1000;
}
export async function deliver(row, request, now = Date.now()) {
  let response;
  try { response = await request('POST', '/api/readings', row.reading); }
  catch { response = {ok:false, status:0}; }
  if (response.ok && response.data?.id === row.id) return {...row, state:'sent', error:null};
  const permanent = [400,409,413,422].includes(response.status);
  const attempts = (row.attempts || 0) + 1;
  return {...row, state:permanent ? 'blocked' : 'pending', attempts,
    retryAt:now + retryDelay(attempts), error:`HTTP ${response.status || 'offline'}`};
}
