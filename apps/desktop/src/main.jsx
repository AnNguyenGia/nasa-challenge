import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {enqueue, entries, sync, cache} from './storage';
import './style.css';
const api = (...args) => window.edge ? window.edge.request(...args) :
  Promise.resolve({ok:false,status:0,error:'Mở bằng Electron để kết nối Edge.'});
function App() {
  const [rows,setRows] = useState([]), [remote,setRemote] = useState([]), [status,setStatus] = useState(null);
  const [online,setOnline] = useState(false), [message,setMessage] = useState(''), [busy,setBusy] = useState(false);
  const [reply,setReply] = useState(''), [asking,setAsking] = useState(false), [question,setQuestion] = useState('');
  const [form,setForm] = useState({astronaut_id:'crew-01',heart_rate:72,temperature:36.7,sleep_hours:7.5,mood:4});
  useEffect(() => {
    let disposed = false, timer;
    async function tick() {
      try {
        await sync(api);
        const local = await entries();
        const [s,r] = await Promise.all([api('GET','/api/status'),api('GET','/api/readings')]);
        if (s.ok) await cache('status',s.data);
        if (r.ok) await cache('readings',r.data);
        const previousStatus = s.ok ? s.data : await cache('status');
        const previousRows = r.ok ? r.data : await cache('readings');
        if (!disposed) {setRows(local);setOnline(s.ok);setStatus(previousStatus);setRemote(previousRows || []);}
      } catch { if (!disposed) setMessage('Không truy cập được bộ nhớ cục bộ. Kiểm tra dung lượng đĩa.'); }
      finally { if (!disposed) timer = setTimeout(tick,3000); }
    }
    tick();
    return () => {disposed=true;clearTimeout(timer);};
  },[]);
  async function save(event) {
    event.preventDefault();setBusy(true);setMessage('');
    try {
      await enqueue({...form,id:crypto.randomUUID(),observed_at:new Date().toISOString()});
      setRows(await entries());setMessage('Đã lưu tại máy. Sẽ tự gửi khi Edge kết nối.');
    } catch {setMessage('Lưu thất bại — bản ghi chưa được lưu. Kiểm tra dung lượng bộ nhớ.');}
    finally {setBusy(false);}
  }
  async function ask(event) {
    event.preventDefault();setAsking(true);
    try {
      const result = await api('POST','/api/agent',{question});
      setReply(result.ok ? `[${result.data.mode}] ${result.data.text}` :
        'Trợ lý chưa sẵn sàng. Kiểm tra phép đo và làm theo quy trình y tế của nhiệm vụ.');
    } finally {setAsking(false);}
  }
  const all = [...new Map([...remote,...rows.map(r=>r.reading)].map(r=>[r.id,r])).values()]
    .sort((a,b)=>b.observed_at.localeCompare(a.observed_at));
  const crewRows = all.filter(r=>r.astronaut_id===form.astronaut_id);
  const latest = crewRows[0];
  const pending = rows.filter(r=>r.state==='pending').length;
  const blocked = rows.filter(r=>r.state==='blocked');
  const trend = crewRows.slice(0,20).reverse();
  return <main>
    <header><div><small>NASA SPACE APPS • PROJECT TEMPLATE</small><h1>Space Health <span>Mission Console</span></h1></div>
      <b className={online?'badge':'badge offline'}>{online?'● Edge online':'● Chế độ cục bộ'}</b></header>
    <p className="notice">Bản demo nghiên cứu · Dữ liệu nhập tay · AI và mô hình tổng hợp không chẩn đoán hoặc kê đơn.</p>
    <section className="stats">{[['Nhịp tim',latest?.heart_rate,'bpm'],['Nhiệt độ',latest?.temperature,'°C'],['Giấc ngủ',latest?.sleep_hours,'giờ'],['Tâm trạng',latest?.mood,'/ 5']].map(([title,value,unit])=><article key={title}><small>{title}</small><strong>{value??'—'} <em>{unit}</em></strong></article>)}</section>
    <div className="columns"><section className="panel"><h2>Ghi nhận sức khỏe</h2><form onSubmit={save}>
      <label>Mã phi hành gia<input required pattern="[a-zA-Z0-9_-]+" maxLength="64" value={form.astronaut_id} onChange={e=>setForm({...form,astronaut_id:e.target.value})}/></label>
      {[['heart_rate','Nhịp tim (bpm)',20,250,1],['temperature','Nhiệt độ (°C)',30,45,.1],['sleep_hours','Ngủ trong 24 giờ (giờ)',0,24,.1],['mood','Tâm trạng: 1 thấp → 5 cao',1,5,1]].map(([key,label,min,max,step])=><label key={key}>{label}<input required type="number" min={min} max={max} step={step} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value===''?'':Number(e.target.value)})}/></label>)}
      <button disabled={busy}>{busy?'Đang lưu…':'Lưu bản ghi tại máy'}</button><p role="status">{message}</p></form>
      <p className="muted">Ghi chỉ số từ thiết bị được phê duyệt; tránh suy luận từ một lần đo. Thời gian lấy theo đồng hồ máy.</p>
    </section><section className="panel"><h2>Diễn biến nhịp tim</h2>
      {trend.length>1?<svg viewBox="0 0 600 180" role="img" aria-label="Biểu đồ nhịp tim, trục dọc 20 đến 250 bpm"><text x="0" y="15">250</text><text x="0" y="175">20</text><polyline fill="none" stroke="#56d9c2" strokeWidth="3" points={trend.map((r,i)=>`${40+i*550/Math.max(1,trend.length-1)},${170-(r.heart_rate-20)/230*155}`).join(' ')}/></svg>:<p>Thêm ít nhất 2 bản ghi để xem biểu đồ.</p>}
      <h2>Kết nối & đồng bộ</h2><ul><li>Chờ Desktop → Edge: <b>{pending}</b></li><li>Chờ Edge → Cloud: <b>{status?.cloud_pending??'—'}</b> {!online?'(trạng thái lưu gần nhất)':''}</li><li>Cloud: {status?.cloud_configured?'đã cấu hình':'chưa cấu hình — hoạt động tại Edge'}</li><li>Lỗi cần kiểm tra: {blocked.length + (status?.dead_letters||0)}</li></ul>
      {blocked.length>0&&<p className="notice">Bản ghi bị từ chối vẫn còn tại máy. Xuất dữ liệu và kiểm tra schema/ID trước khi gửi lại.</p>}
      <button className="secondary" onClick={async()=>{const blob=new Blob([JSON.stringify(await entries(),null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='health-local-export.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}}>Xuất bản sao dữ liệu cục bộ</button>
      <h2>Phân tích tại Edge</h2><p>{status?.assessments?.find(a=>a.reading_id===latest?.id)?.message || 'Chờ sự kiện được xử lý hoặc chưa có mô hình.'}</p>
    </section></div>
    <section className="panel"><h2>Trợ lý Qwen tại Edge</h2><form onSubmit={ask} className="ask"><input aria-label="Câu hỏi cho Qwen" required maxLength="2000" placeholder="Hướng dẫn ghi nhật ký giấc ngủ…" value={question} onChange={e=>setQuestion(e.target.value)}/><button disabled={asking}>{asking?'Đang xử lý…':'Hỏi trợ lý'}</button></form><p className="reply" role="status">{reply}</p></section>
    <section className="panel"><h2>Bản ghi gần đây</h2><table><thead><tr><th>Thời gian</th><th>Phi hành gia</th><th>bpm</th><th>°C</th><th>Ngủ</th><th>Trạng thái</th></tr></thead><tbody>{all.slice(0,20).map(r=><tr key={r.id}><td>{new Date(r.observed_at).toLocaleString('vi-VN')}</td><td>{r.astronaut_id}</td><td>{r.heart_rate}</td><td>{r.temperature}</td><td>{r.sleep_hours}</td><td>{rows.find(x=>x.id===r.id)?.state||'edge'}</td></tr>)}</tbody></table></section>
  </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
